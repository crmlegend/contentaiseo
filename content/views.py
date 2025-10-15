import logging, time, uuid
from pprint import pprint
import time

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from billing.auth import ApiKeyAuthentication
from billing.permissions import IsSubscriber
from .serializers import GenPayload, BlogPreviewPayload
from .services import (
    norm_site, upsert_keys_for_site, get_site_keys, resolve_provider_and_model,
    clamp_temperature, ai_text, ai_blog_json, make_blog_prompt, render_preview_html
)
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework import status
import logging, re, time
from billing.auth import ApiKeyAuthentication
from billing.permissions import IsSubscriber
from .serializers import GenPayload, BlogPreviewPayload
from .services import (
    norm_site, upsert_keys_for_site, get_site_keys, resolve_provider_and_model,
    clamp_temperature, ai_text, ai_blog_json, make_blog_prompt, render_preview_html
)


logger = logging.getLogger(__name__)

def _safe_bool(v):  # show True/False only
    return bool(v) and True or False

def _cid(request):
    """Correlation id to trace a single request through logs."""
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())

def _safe_opts(opts: dict):
    """Never log prompt/reference text; show only lengths + model-ish toggles."""
    if not isinstance(opts, dict): return {}
    out = {}
    for k, v in opts.items():
        if k in {"prompt", "reference_text", "sitemap_url"}:
            # just show length to prove data arrived
            out[k + "_len"] = len((v or "").strip())
        elif k == "temperature":
            out[k] = v
        elif k == "mode":
            out[k] = v
        else:
            # short/primitive values are safe; avoid dumping nested dicts
            out[k] = v if isinstance(v, (str, int, float, bool)) else type(v).__name__
    return out










logger = logging.getLogger(__name__)

def _safe_bool(x): return bool(x)
def _safe_opts(opts):
    try:
        # Don’t dump whole payload; show only small summary
        keys = list((opts or {}).keys())
        return {"keys": keys[:10], "len": len(keys)}
    except Exception:
        return {}

def _cid(request):
    # Try to tag logs with a per-request id (from header or create quickly)
    return request.headers.get("X-Request-Id") or f"cid-{int(time.time()*1000)}"
















# views.py

import re, time, logging
from pprint import pprint
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


@api_view(["POST"])
@authentication_classes([ApiKeyAuthentication])
@permission_classes([IsSubscriber])
def generate(request):
    # ===== DIAGNOSTIC LOGGING (safe) =====
    print("\n===== REQUEST START =====")
    print(f"Method: {request.method}")
    print(f"Path:   {request.get_full_path()}")
    print(f"User:   {getattr(request.user, 'username', request.user)}")

    print("\n-- HEADERS --")
    try:
        pprint(dict(request.headers))
    except Exception:
        pass

    print("\n-- QUERY PARAMS --")
    try:
        pprint(request.query_params.dict())
    except Exception:
        try:
            pprint(dict(request.query_params))
        except Exception:
            pass

    print("\n-- PARSED DATA (request.data) --")
    try:
        # Avoid logging gigantic JSON blobs fully; trim if needed
        preview = request.data
        if isinstance(preview, dict) and "elementor" in preview:
            # Show only counts/types to keep logs tidy
            el = preview.get("elementor")
            preview = dict(preview)
            preview["elementor"] = f"<array len={len(el) if isinstance(el, list) else 'n/a'}>"
        pprint(preview)
    except Exception as e:
        print("Could not read request.data:", e)

    print("\n-- RAW BODY (request.body) --")
    try:
        print(request.body.decode("utf-8", errors="replace")[:4000])  # cap
    except Exception as e:
        print("Could not decode raw body:", e)

    print("\n-- FILES --")
    try:
        pprint({k: f"{f.name} ({getattr(f, 'size', '?')} bytes)" for k, f in request.FILES.items()})
    except Exception:
        pprint({})

    print("\n-- META --")
    try:
        pprint(request.META)
    except Exception:
        pass
    print("===== REQUEST END =====\n")
    # =====================================

    cid = _cid(request)
    t0  = time.time()

    try:
        # ------- Minimal, Elementor-only payload -------
        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "JSON body required."})

        data      = request.data
        prompt    = str(data.get("prompt") or "")
        elementor = data.get("elementor")

        if not isinstance(elementor, list):
            raise ValidationError({"elementor": "Must be an array matching Elementor JSON structure."})

        # Optional: site + provider/model/temperature (kept, but minimal)
        site         = norm_site(str(data.get("site") or "")) if "site" in data else ""
        opts         = data.get("options") or {}
        provider, model = resolve_provider_and_model(opts, site)
        temperature  = clamp_temperature(opts.get("temperature") or 0.7)

        # Upsert keys from headers/body (same idea as your PHP `provider_headers`)
        upsert_keys_for_site(site, data.get("openai_key"), data.get("gemini_key"))
        upsert_keys_for_site(site, request.headers.get("X-OpenAI-Key"), request.headers.get("X-Gemini-Key"))

        keys = get_site_keys(site) if site else {"openai_key": request.headers.get("X-OpenAI-Key"), "gemini_key": request.headers.get("X-Gemini-Key")}
        if provider == "openai" and not keys.get("openai_key"):
            logger.warning("gen: missing_openai_key cid=%s site=%s", cid, site)
            return Response({"detail": "OpenAI key missing."}, status=400)
        if provider == "gemini" and not keys.get("gemini_key"):
            logger.warning("gen: missing_gemini_key cid=%s site=%s", cid, site)
            return Response({"detail": "Gemini key missing."}, status=400)

        logger.info("gen: elementor start cid=%s site=%s provider=%s model=%s", cid, site, provider, model)

        # ------- Allowed widgets/fields (mirror of your PHP) -------
        ALLOWED = {
            "heading": [
                {"key": "title", "html": False, "shape": "string", "purpose": "headline"},
            ],
            "text-editor": [
                {"key": "editor", "html": True, "shape": "string", "purpose": "html"},
            ],
            "button": [
                {"key": "text", "html": False, "shape": "string", "purpose": "label"},
            ],
            "icon-box": [
                {"key": "title_text", "html": False, "shape": "string", "purpose": "headline"},
                {"key": "description_text", "html": True, "shape": "string", "purpose": "paragraph"},
            ],
            "image-box": [
                {"key": "title_text", "html": False, "shape": "string", "purpose": "headline"},
                {"key": "description_text", "html": True, "shape": "string", "purpose": "paragraph"},
            ],
            "testimonial": [
                {"key": "testimonial_content", "html": True, "shape": "string", "purpose": "paragraph"},
                {"key": "testimonial_name", "html": False, "shape": "string", "purpose": "label"},
                {"key": "testimonial_job", "html": False, "shape": "string", "purpose": "label"},
            ],
            "alert": [
                {"key": "alert_title", "html": False, "shape": "string", "purpose": "headline"},
                {"key": "alert_description", "html": True, "shape": "string", "purpose": "paragraph"},
            ],
            "html": [
                {"key": "html", "html": True, "shape": "string", "purpose": "html"},
            ],
            # Repeaters
            "accordion": [
                {"key": "tabs[].tab_title", "html": False, "shape": "string_or_raw", "purpose": "headline"},
                {"key": "tabs[].tab_content", "html": True, "shape": "string", "purpose": "html"},
            ],
            # NEW: nested-accordion & icon-list
            "nested-accordion": [
                {"key": "items[].item_title", "html": False, "shape": "string_or_raw", "purpose": "headline"},
            ],
            "icon-list": [
                {"key": "icon_list[].text", "html": False, "shape": "string_or_raw", "purpose": "label"},
            ],
        }

        repeater_re = re.compile(r"^([a-z0-9_]+)\[\]\.([a-z0-9_]+)$", re.I)

        def _get_raw_or_string(val):
            """Preserve Elementor's {'raw': '...'} when present."""
            if isinstance(val, dict):
                return str(val.get("raw") or "")
            return str(val or "")

        def _put_back_raw_or_string(settings, key, original_value, new_value):
            """Write back to settings preserving raw-shape if the original was a dict."""
            if isinstance(original_value, dict):
                if key not in settings or not isinstance(settings[key], dict):
                    settings[key] = {}
                settings[key]["raw"] = new_value
            else:
                settings[key] = new_value

        def build_prompt(widget_type, field_key, original, is_html):
            block = "HTML" if is_html else "TEXT"
            instructions = prompt
            return (
                f"Rewrite the following {block} according to these instructions:\n"
                f"Instructions: {instructions}\n\n\n"
                f"BEGIN_ORIGINAL_{block}\n\n\n{original}\n\n\nEND_ORIGINAL_{block}\n"
                f"Return ONLY the rewritten {block} in the same format as the original and do not include any additional text or any additional signs [like html or text or any additional quotes, just give me the plain and professional {block}."
            )

        def traverse(elements):
            if not isinstance(elements, list):
                return elements
            out = []
            for el in elements:
                if not isinstance(el, dict):
                    out.append(el)
                    continue

                # Process widgets
                if el.get("elType") == "widget" and isinstance(el.get("settings"), dict):
                    widget_type = el.get("widgetType") or ""
                    settings    = dict(el["settings"])  # copy

                    rules = ALLOWED.get(widget_type) or []
                    for rule in rules:
                        key     = rule.get("key")
                        is_html = bool(rule.get("html"))
                        shape   = (rule.get("shape") or "string")

                        # Repeater pattern: e.g., tabs[].tab_title
                        m = repeater_re.match(key or "")
                        if m:
                            rep_key, item_key = m.group(1), m.group(2)
                            rep_list = settings.get(rep_key)
                            if isinstance(rep_list, list):
                                for idx in range(len(rep_list)):
                                    item = rep_list[idx]
                                    if not isinstance(item, dict) or item_key not in item:
                                        continue
                                    orig_val = item[item_key]
                                    current  = _get_raw_or_string(orig_val) if shape == "string_or_raw" else str(orig_val or "")
                                    if not current:
                                        continue

                                    try:
                                        ptxt      = build_prompt(widget_type, key, current, is_html)
                                        rewritten = ai_text(ptxt, model, provider, site, temperature)
                                    except Exception:
                                        logger.exception("ai_text failed (repeater) cid=%s site=%s widget=%s key=%s", cid, site, widget_type, key)
                                        raise

                                    # Put back preserving shape
                                    if shape == "string_or_raw":
                                        if isinstance(orig_val, dict):
                                            if not isinstance(item.get(item_key), dict):
                                                item[item_key] = {}
                                            item[item_key]["raw"] = rewritten
                                        else:
                                            item[item_key] = rewritten
                                    else:
                                        item[item_key] = rewritten
                            # proceed to next rule
                            continue

                        # Flat key
                        if key in settings:
                            orig_val = settings[key]
                            current  = _get_raw_or_string(orig_val) if shape == "string_or_raw" else str(orig_val or "")
                            if current:
                                try:
                                    ptxt      = build_prompt(widget_type, key, current, is_html)
                                    rewritten = ai_text(ptxt, model, provider, site, temperature)
                                except Exception:
                                    logger.exception("ai_text failed (flat) cid=%s site=%s widget=%s key=%s", cid, site, widget_type, key)
                                    raise

                                if shape == "string_or_raw":
                                    _put_back_raw_or_string(settings, key, orig_val, rewritten)
                                else:
                                    settings[key] = rewritten

                    # write back settings
                    el["settings"] = settings

                # Recurse into children
                if isinstance(el.get("elements"), list):
                    el["elements"] = traverse(el["elements"])

                out.append(el)
            return out

        t1 = time.time()
        try:
            updated = traverse(elementor)
        except Exception as e:
            logger.error("gen: traverse failed cid=%s site=%s err=%s", cid, site, str(e), exc_info=True)
            return Response({"detail": "AI processing failed while rewriting Elementor content."}, status=400)

        elapsed = time.time() - t1
        logger.info("gen: elementor_ok cid=%s site=%s elapsed=%.2fs", cid, site, elapsed)
        logger.info("gen: done cid=%s total=%.2fs", cid, time.time() - t0)

        # Exactly what your PHP client expects:
        # process_elementor() -> do_post() expects {"elementor": [...]}
        return Response({"elementor": updated}, status=200)

    except ValidationError as e:
        logger.warning("gen: validation cid=%s detail=%s", cid, e.detail)
        raise
    except Exception as e:
        logger.error("gen: failed cid=%s err=%s", cid, str(e), exc_info=True)
        return Response({"detail": "AI provider error. See server logs."}, status=400)




































@api_view(["POST"])
@authentication_classes([ApiKeyAuthentication])
@permission_classes([IsSubscriber])
def blog_preview(request):
    """
    Generate blog preview HTML (same AI path but returns rendered HTML).
    """
    print("request receieved successfully ")
    cid = _cid(request)
    t0 = time.time()
    try:
        s = BlogPreviewPayload(data=request.data); s.is_valid(raise_exception=True)
        data = s.validated_data

        site = norm_site(data.get("site") or "")
        upsert_keys_for_site(site, data.get("openai_key"), data.get("gemini_key"))
        upsert_keys_for_site(site, request.headers.get("X-Openai-Key"), request.headers.get("X-Gemini-Key"))

        opts = data.get("options") or {}
        provider, model = resolve_provider_and_model(opts, site)
        temperature = clamp_temperature(opts.get("temperature") or 0.7)

        keys = get_site_keys(site)
        logger.info(
            "bp: start cid=%s site=%s provider=%s model=%s keys(openai=%s,gemini=%s) opts=%s",
            cid, site, provider, model, _safe_bool(keys.get("openai_key")), _safe_bool(keys.get("gemini_key")),
            _safe_opts(opts)
        )

        if provider == "openai" and not keys["openai_key"]:
            logger.warning("bp: missing_openai_key cid=%s site=%s", cid, site)
            return Response({"detail": "OpenAI key missing for this site."}, status=400)
        if provider == "gemini" and not keys["gemini_key"]:
            logger.warning("bp: missing_gemini_key cid=%s site=%s", cid, site)
            return Response({"detail": "Gemini key missing for this site."}, status=400)

        t1 = time.time()
        composite = make_blog_prompt(
            data.get("prompt") or "",
            (opts.get("reference_text") or "").strip(),
            (opts.get("sitemap_url") or "").strip()
        )
        doc = ai_blog_json(composite, model, provider, site, temperature)
        html = render_preview_html(doc)
        elapsed = time.time() - t1

        logger.info("bp: ok cid=%s site=%s elapsed=%.2fs title_len=%d html_len=%d",
                    cid, site, elapsed, len(doc.get("title") or ""), len(html or ""))
        logger.info("bp: done cid=%s total=%.2fs", cid, time.time() - t0)
        return Response({"html": html, "title": doc.get("title")})

    except ValidationError as e:
        logger.warning("bp: validation cid=%s site=%s detail=%s", cid, locals().get("site", ""), e.detail)
        raise
    except Exception as e:
        logger.error("bp: failed cid=%s site=%s err=%s", cid, locals().get("site", ""), str(e), exc_info=True)
        return Response({"detail": "AI provider error. See server logs."}, status=400)
