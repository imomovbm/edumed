"""Optional Claude AI analysis for the profile page ("AI orqali baholash").

Switched on by setting ANTHROPIC_API_KEY in .env (and ``pip install anthropic``).
Only anonymous learning statistics are sent — never names, e-mails, phone
numbers, birth dates or regions.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback (`fallbacks="default"`).
_FALLBACK_MODELS = ('claude-opus-5-5', 'claude-opus-5', 'claude-sonnet-5-5', 'claude-fable-5-1')

SYSTEM_PROMPT = (
    "You are a supportive learning adviser for EDUMED.UZ, an online platform that trains "
    "future nurses in Uzbekistan. You receive anonymous statistics about one student's quiz "
    "results, topic progress and forum activity as JSON. Write a short analysis for the "
    "student in Uzbek (Latin script), addressing them as \"siz\".\n\n"
    "Structure the answer as plain text with exactly these three headings, each on its own "
    "line: \"Kuchli tomonlar:\", \"Rivojlantirish kerak:\", \"Tavsiyalar:\". Under each heading "
    "write 2-4 lines that start with \"- \". Base every point on the numbers you were given and "
    "name the topics they refer to; compare with the platform average when it helps. If there "
    "is little data, say so briefly and suggest which topics to start with. Keep the whole "
    "answer under 200 words. Do not use Markdown symbols such as # or ** and do not invent "
    "facts that are not in the data."
)


class AIUnavailable(Exception):
    """Raised with a message that can be shown to the user."""


def is_enabled():
    return bool(getattr(settings, 'ANTHROPIC_API_KEY', ''))


def build_student_payload(ctx):
    """Anonymous statistics from the profile context (see user.views._build_profile_context)."""
    topics = []
    for item in ctx['topic_progress_data']:
        topics.append({
            'mavzu': item['title'],
            'holat': item['status'],
            'ozlashtirish_foiz': item['pct'],
            'testlar_soni': item['quiz_count'],
            'talaba_ortacha_ball': item['user_avg'],
            'platforma_ortacha_ball': item['platform_avg'],
        })
    recent = [
        {
            'test': r.quiz.title if r.quiz else "o'chirilgan test",
            'ball': r.score,
            'togri': r.correct_count,
            'notogri': r.incorrect_count,
            'belgilanmagan': r.skipped_count,
        }
        for r in ctx['responses'][:10]
    ]
    return {
        'topshirilgan_testlar': ctx['total_responses'],
        'ortacha_ball': ctx['avg_score'],
        'ball_taqsimoti': {
            'alo_90_100': ctx['score_a'], 'yaxshi_70_89': ctx['score_b'],
            'qoniqarli_50_69': ctx['score_c'], 'qoniqarsiz_0_49': ctx['score_d'],
        },
        'umumiy_ozlashtirish_foiz': ctx['overall_progress'],
        'tugatilgan_mavzular': ctx['completed_topics'],
        'jami_mavzular': ctx['total_topics'],
        'forum_izohlari': ctx['forum_comments'],
        'mavzular': topics,
        'songgi_testlar': recent,
    }


def generate_analysis(payload):
    """Ask Claude for the analysis text. Raises AIUnavailable on any problem."""
    if not is_enabled():
        raise AIUnavailable("AI tahlili hozircha yoqilmagan.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on the server setup
        raise AIUnavailable("AI kutubxonasi o'rnatilmagan (pip install anthropic).") from exc

    model = settings.ANTHROPIC_MODEL
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=60.0, max_retries=1)
    request = dict(
        model=model,
        max_tokens=16000,
        output_config={'effort': 'low'},  # short, data-bound summary; keeps the page fast
        system=SYSTEM_PROMPT,
        messages=[{
            'role': 'user',
            'content': json.dumps(payload, ensure_ascii=False, indent=1),
        }],
    )
    try:
        if model in _FALLBACK_MODELS:
            # If a safety classifier declines, the API re-runs the request on a
            # fallback model inside the same call.
            message = client.beta.messages.create(
                betas=['server-side-fallback-2026-07-01'], fallbacks='default', **request,
            )
        else:
            message = client.messages.create(**request)
    except anthropic.AuthenticationError as exc:
        logger.error("Claude API key rejected: %s", exc)
        raise AIUnavailable("AI xizmati sozlanmagan (API kalit noto'g'ri).") from exc
    except anthropic.RateLimitError as exc:
        raise AIUnavailable("AI xizmati band. Birozdan so'ng qayta urinib ko'ring.") from exc
    except anthropic.APITimeoutError as exc:
        raise AIUnavailable("AI javobi kechikdi. Qayta urinib ko'ring.") from exc
    except anthropic.APIConnectionError as exc:
        logger.warning("Claude API connection error: %s", exc)
        raise AIUnavailable("AI xizmatiga ulanib bo'lmadi.") from exc
    except anthropic.APIStatusError as exc:
        logger.error("Claude API error %s: %s", exc.status_code, exc)
        raise AIUnavailable("AI xizmatida xatolik yuz berdi.") from exc

    if message.stop_reason == 'refusal':
        raise AIUnavailable("AI bu so'rov bo'yicha tahlil bera olmadi.")
    text = ''.join(block.text for block in message.content if block.type == 'text').strip()
    if not text:
        raise AIUnavailable("AI bo'sh javob qaytardi. Qayta urinib ko'ring.")
    return text
