"""
Resume generation: fetch the right resume data live from the resume app, tailor it to
a specific job with Claude, and render the result to PDF/DOCX via the same
resume app. See DEPLOYMENT.md / README.md for the INTERNAL_API_TOKEN and
ANTHROPIC_API_KEY setup this depends on.

Nothing here touches the resume app's actual resume files or site/ output -
every render happens into a throwaway temp directory on that end (see
resume/app/admin.py). This module only ever reads from the resume app and
sends it ad-hoc tailored data to render.
"""
import json
import re
from typing import Tuple

import anthropic
import httpx
import yaml

from . import config


class ResumeGenerationError(Exception):
    """Missing config, a fetch/render failure talking to the resume app, or
    a Claude response that never became valid JSON even after one repair
    attempt. Always has a message safe to show directly in the UI."""


def _require_internal_token() -> str:
    if not config.INTERNAL_API_TOKEN:
        raise ResumeGenerationError(
            "INTERNAL_API_TOKEN is not set - can't reach the resume app. "
            "See README.md for setup."
        )
    return config.INTERNAL_API_TOKEN


def fetch_resume_data(resume_person_slug: str = None) -> dict:
    """The resume app's default person's data, as a dict - or a specific
    household member's own data (resume_person_slug, e.g. "rach", from
    Person.resume_person_slug) when generating for a job owned by someone
    other than the default person. Fetched live on every call rather than
    cached, so an edit made through the resume app's People admin UI is
    always picked up immediately."""
    token = _require_internal_token()
    params = {"person": resume_person_slug} if resume_person_slug else {}
    try:
        resp = httpx.get(
            f"{config.RESUME_ADMIN_URL}/api/resume-data",
            headers={"X-Internal-Token": token},
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ResumeGenerationError(
                f"The resume app has no person with slug {resume_person_slug!r} - "
                "check this person's Settings entry."
            )
        raise ResumeGenerationError(f"Could not reach the resume app at {config.RESUME_ADMIN_URL}: {e}")
    except httpx.HTTPError as e:
        raise ResumeGenerationError(
            f"Could not reach the resume app at {config.RESUME_ADMIN_URL}: {e}"
        )
    return resp.json()


def list_resume_people() -> list:
    """Every person the resume app currently has, as {slug, name,
    is_default} - source list for the People admin page's per-person resume
    dropdown."""
    token = _require_internal_token()
    try:
        resp = httpx.get(
            f"{config.RESUME_ADMIN_URL}/api/resume-people",
            headers={"X-Internal-Token": token},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ResumeGenerationError(
            f"Could not reach the resume app at {config.RESUME_ADMIN_URL}: {e}"
        )
    return resp.json()["people"]


def render_document(resume_data: dict, fmt: str) -> bytes:
    """Render resume-shaped data into PDF or DOCX bytes via the resume
    app's rendering pipeline. fmt is "pdf" or "docx"."""
    token = _require_internal_token()
    try:
        resp = httpx.post(
            f"{config.RESUME_ADMIN_URL}/api/render",
            headers={"X-Internal-Token": token},
            json={"data": resume_data, "format": fmt},
            timeout=60.0,  # headless Chromium launch + print can take a few seconds
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = e.response.text
        try:
            detail = e.response.json().get("detail", detail)
        except ValueError:
            pass
        raise ResumeGenerationError(f"Resume app couldn't render the {fmt}: {detail}")
    except httpx.HTTPError as e:
        raise ResumeGenerationError(
            f"Could not reach the resume app at {config.RESUME_ADMIN_URL}: {e}"
        )
    return resp.content


SYSTEM_PROMPT = """You tailor a resume to a specific job description and write a matching cover letter.

Rules:
- Never invent experience, employers, titles, dates, or skills that aren't in the source resume. You may reorder, re-emphasize, trim, or rephrase existing bullets to foreground what's relevant to this job - you may not fabricate new accomplishments.
- Keep everything in "basics" (name, contact info, links, title) exactly as given - never edit contact details. You may lightly adjust the summary paragraph to emphasize relevant strengths, without inventing anything.
- Keep the same top-level structure as the resume you were given (the same keys - e.g. basics/experience/education/skills/certifications/projects if present) - only the content within experience bullets, skills ordering, and the summary should change.
- Write a cover letter: 3-4 short paragraphs, no placeholder brackets like [Company Name], addressed generically (no "Dear Hiring Manager" - open with something specific to the role instead) that connects the candidate's real background to this specific job.
- Respond with ONLY a single JSON object, no markdown code fences, no commentary before or after it: {"resume": <the tailored resume, same shape as the input>, "cover_letter": <string>}
"""


def _build_user_message(resume_data: dict, job) -> str:
    parts = [
        f"Job title: {job.name}",
        f"Company: {job.company or 'Unknown'}",
    ]
    if job.salary:
        parts.append(f"Salary: {job.salary}")
    parts.append(
        "\nJob description:\n"
        + (job.jd_text or "(no job description text was captured for this listing - "
           "tailor based on the title and company alone)")
    )
    parts.append("\nSource resume (JSON):\n" + json.dumps(resume_data))
    return "\n".join(parts)


def _extract_json(text: str) -> str:
    """Strip a ```json ... ``` fence if the model wrapped the output in one
    despite being asked not to - cheap insurance, not a substitute for the
    plain-JSON instruction."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1) if match else text


def _tailor(resume_data: dict, job) -> Tuple[dict, str]:
    """Call Claude to tailor resume_data to job's JD. Returns
    (tailored_resume_dict, cover_letter_text). One repair attempt if the
    response isn't valid JSON before giving up."""
    if not config.ANTHROPIC_API_KEY:
        raise ResumeGenerationError(
            "ANTHROPIC_API_KEY is not set - resume generation is unavailable. "
            "See README.md for setup."
        )
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": _build_user_message(resume_data, job)}]

    for attempt in range(2):
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        raw = "".join(block.text for block in response.content if block.type == "text")
        candidate = _extract_json(raw)
        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict) or "resume" not in parsed or "cover_letter" not in parsed:
                raise ValueError("response JSON is missing 'resume' or 'cover_letter'")
            return parsed["resume"], parsed["cover_letter"]
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        f"That wasn't valid JSON ({e}). Respond again with ONLY the JSON "
                        "object described above - no markdown fences, no other text."
                    ),
                })
                continue
            raise ResumeGenerationError(
                f"Claude's response wasn't usable JSON, even after a retry: {e}"
            )


def generate_for_job(job) -> Tuple[str, str]:
    """Full flow for one job: fetch the right resume data live (the job
    owner's own person if they've picked one in People, else the resume
    app's default person), tailor it to the job, return
    (tailored_resume_yaml_text, cover_letter_text) ready to store on the Job
    row. Raises ResumeGenerationError on any failure - callers should not
    partially save state on error."""
    resume_person_slug = job.owner.resume_person_slug if job.owner else None
    resume_data = fetch_resume_data(resume_person_slug)
    tailored, cover_letter = _tailor(resume_data, job)
    tailored_yaml = yaml.safe_dump(tailored, sort_keys=False, allow_unicode=True)
    return tailored_yaml, cover_letter
