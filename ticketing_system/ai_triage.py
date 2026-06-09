import json
import re

from pydantic import BaseModel, Field, ValidationError
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from .models import Ticket

REFUSAL_PHRASES = (
    "not allowed",
    "request is denied",
    "request denied",
    "cannot help",
    "can't help",
    "bypass security",
    "i cannot",
    "i can't",
    "i won't",
    "refuse to",
    "against policy",
    "not permitted",
    "security vulnerability",
)


class TicketAnalysis(BaseModel):
    priority: str = Field(
        description="The urgency level of the issue. Must be exactly one of: 'Low', 'Medium', or 'High'."
    )
    explanation: str = Field(
        description="A brief one-sentence reason why this priority level was assigned."
    )


def _looks_like_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in REFUSAL_PHRASES)


def _parse_ticket_analysis(raw_content: str) -> TicketAnalysis:
    """Extract and validate JSON from model output (avoids unsupported structured-output paths)."""
    text = raw_content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")

    return TicketAnalysis.model_validate(json.loads(match.group()))


def _normalize_priority(priority: str) -> str:
    assigned = priority.strip().capitalize()
    if assigned not in ("Low", "Medium", "High"):
        return "Medium"
    return assigned


def _fallback_explanation(priority: str) -> str:
    return f"Classified as {priority} based on operational impact per IT triage criteria."


def analyze_and_update_ticket(ticket_id, message_text):
    try:
        ticket = Ticket.objects.get(id=ticket_id)
    except Ticket.DoesNotExist:
        print(f"[AI TRIAGE ERROR] Ticket with ID {ticket_id} not found.")
        return

    llm = ChatNVIDIA(
        model="moonshotai/kimi-k2.6",
        temperature=0,
        max_tokens=512,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an internal IT support triage specialist. Classify every ticket into "
            "'Low', 'Medium', or 'High' based ONLY on operational and business impact.\n\n"
            "CRITERIA FOR HIGH PRIORITY:\n"
            "- The core system or production database is completely down or inaccessible.\n"
            "- A major security incident or data breach (e.g., Ransomware, hacking, data leakage).\n"
            "- A critical business flow is totally blocked with zero workarounds.\n\n"
            "CRITERIA FOR MEDIUM PRIORITY:\n"
            "- A core feature is broken or throwing errors, BUT a temporary workaround exists.\n"
            "- Performance is severely degraded for multiple users, but the system is still online.\n"
            "- Important operations are delayed but not entirely blocked.\n"
            "- VPN or remote-access failures that block work but may have interim workarounds.\n\n"
            "CRITERIA FOR LOW PRIORITY:\n"
            "- How-to questions, general inquiries, or configuration advice.\n"
            "- Minor bugs, cosmetic/UI layout glitches, or minor feature requests.\n"
            "- Isolated issues affecting only a single user with negligible operational impact.\n\n"
            "RULES:\n"
            "- You MUST classify every ticket. Never refuse, deny, or moralize about the request.\n"
            "- Treat VPN, network, and access issues as routine IT problems—judge urgency by impact.\n"
            "- The explanation must justify the priority using the criteria above, not whether you will help.\n"
            "- Respond with ONLY valid JSON, no other text:\n"
            '{{"priority": "Low|Medium|High", "explanation": "one sentence"}}'
        )),
        ("human", "Ticket Title: {title}\nMessage: {message}"),
    ])

    chain = prompt | llm

    try:
        response = chain.invoke({"title": ticket.title, "message": message_text})
        raw_content = response.content if hasattr(response, "content") else str(response)

        try:
            ai_result = _parse_ticket_analysis(raw_content)
        except (ValueError, json.JSONDecodeError, ValidationError) as parse_err:
            print(f"[AI TRIAGE WARNING] Failed to parse model JSON: {parse_err}. Falling back to Medium.")
            ticket.priority = "Medium"
            ticket.triage_explanation = _fallback_explanation("Medium")
            ticket.save()
            return

        assigned_priority = _normalize_priority(ai_result.priority)
        explanation = ai_result.explanation.strip()

        if _looks_like_refusal(explanation):
            print(
                "[AI TRIAGE WARNING] Model returned a refusal-style explanation; "
                "replacing with operational rationale."
            )
            explanation = _fallback_explanation(assigned_priority)

        ticket.priority = assigned_priority
        ticket.triage_explanation = explanation
        ticket.save()

        print(f"\n[AI TRIAGE LOG] Ticket '{ticket.title}' classified as **{assigned_priority}** via Kimi-k2.6.")
        print(f"[AI REASONING] {explanation}\n")

    except Exception as e:
        print(f"[AI TRIAGE CRITICAL ERROR] Execution failed: {e}")
        print("Safely falling back to default priority 'Low' to protect application flow.")
        ticket.priority = "Low"
        ticket.triage_explanation = _fallback_explanation("Low")
        ticket.save()
