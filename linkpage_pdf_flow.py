#!/usr/bin/env python3
"""
Linkpages as PDF Collection — End-to-End API Flow
==================================================
Converts the Postman collection "POC: Linkpages as PDF collection" into a
sequential Python script where each step feeds its output into the next.

Dependencies: pip install requests
Usage:
    python linkpage_pdf_flow.py \
        --token "YOUR_API_KEY" \
        --org-id 949 \
        --pdf-path /path/to/sample.pdf \
        --linkpage-name "Hersheys TLC 101" \
        --qr-name "QR: Hersheys 10001"

You can also set env vars instead of CLI args:
    UNIQODE_TOKEN, UNIQODE_ORG_ID, UNIQODE_ENV (qa|prod)
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ENV_CONFIG = {
    "qa": {
        "base_url": "https://beaconstacqa.mobstac.com/api/2.0",
        "pdf_base_url": "https://q.eddy.pro",
    },
    "prod": {
        "base_url": "https://api.uniqode.com/api/2.0",
        "pdf_base_url": "https://eddy.pro",
    },
}

_env = os.getenv("UNIQODE_ENV", "qa").lower()
BASE_URL = ENV_CONFIG.get(_env, ENV_CONFIG["qa"])["base_url"]
PDF_BASE_URL = ENV_CONFIG.get(_env, ENV_CONFIG["qa"])["pdf_base_url"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def auth_headers(token: str, content_type: str = "application/json") -> dict:
    """Return standard auth + content-type headers."""
    return {
        "Authorization": f"Token {token}",
        "Content-Type": content_type,
    }


def check_response(resp: requests.Response, step: str):
    """Log and raise on non-2xx responses."""
    if not resp.ok:
        log.error(
            "STEP [%s] FAILED — %s %s\nStatus: %s\nBody:\n%s",
            step,
            resp.request.method,
            resp.url,
            resp.status_code,
            resp.text[:2000],
        )
        resp.raise_for_status()
    log.info("STEP [%s] ✓  %s", step, resp.status_code)


def pretty(data: dict) -> str:
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Step 1 — Create a Linkpage
# ---------------------------------------------------------------------------
def create_linkpage(token: str, org_id: int, name: str) -> dict:
    """
    POST /api/2.0/linkpage/
    Returns the full linkpage object. Key fields extracted downstream:
      - id          → linkpage_id
      - url         → linkpage_url  (e.g. https://q.linkpages.pro/xxxxx)
    """
    log.info("━" * 60)
    log.info("STEP 1 — Create Linkpage: %s", name)
    url = f"{BASE_URL}/linkpage/"
    payload = {"name": name, "organization": org_id}
    resp = requests.post(url, headers=auth_headers(token), json=payload)
    check_response(resp, "1-create-linkpage")
    data = resp.json()
    log.info("  Linkpage ID  : %s", data.get("id"))
    log.info("  Linkpage URL : %s", data.get("url"))
    return data


# ---------------------------------------------------------------------------
# Step 2 — Create QR Code linked to the Linkpage
# ---------------------------------------------------------------------------
def create_qr_code(token: str, org_id: int, linkpage_id: int, qr_name: str) -> dict:
    """
    POST /api/2.0/qrcodes/?organization={org_id}
    Returns the QR code object. Key field:
      - id → qr_code_id
    """
    log.info("━" * 60)
    log.info("STEP 2 — Create QR Code: %s (linkpage=%s)", qr_name, linkpage_id)
    url = f"{BASE_URL}/qrcodes/?organization={org_id}"
    payload = {
        "campaign": {
            "content_type": 18,
            "campaign_active": True,
            "timezone": "Asia/Calcutta",
            "organization": org_id,
            "link_page": linkpage_id,
            "age_gate": 0,
        },
        "qr_type": 2,
        "organization": org_id,
        "name": qr_name,
    }
    resp = requests.post(url, headers=auth_headers(token), json=payload)
    check_response(resp, "2-create-qr")
    data = resp.json()
    log.info("  QR Code ID : %s", data.get("id"))
    return data


# ---------------------------------------------------------------------------
# Step 2.1 — Get QR Details
# ---------------------------------------------------------------------------
def get_qr_details(token: str, qr_code_id: int) -> dict:
    """
    GET /api/2.0/qrcodes/{qr_code_id}
    """
    log.info("━" * 60)
    log.info("STEP 2.1 — Get QR Details: %s", qr_code_id)
    url = f"{BASE_URL}/qrcodes/{qr_code_id}"
    resp = requests.get(url, headers=auth_headers(token))
    check_response(resp, "2.1-get-qr-details")
    data = resp.json()
    log.info("  QR Name    : %s", data.get("name"))
    log.info("  QR URL     : %s", data.get("url", "N/A"))
    return data


# ---------------------------------------------------------------------------
# Step 2.2 — Download QR Image (PDF format)
# ---------------------------------------------------------------------------
def download_qr_image(
    token: str,
    qr_code_id: int,
    output_dir: str = ".",
    size: int = 1024,
    error_correction: int = 2,
    canvas_type: str = "pdf",
) -> str:
    """
    GET /api/2.0/qrcodes/{qr_code_id}/download/?size=...&error_correction_level=...&canvas_type=...
    Saves the file locally and returns the file path.
    """
    log.info("━" * 60)
    log.info("STEP 2.2 — Download QR Image (format=%s)", canvas_type)
    params = {
        "size": size,
        "error_correction_level": error_correction,
        "canvas_type": canvas_type,
    }
    url = f"{BASE_URL}/qrcodes/{qr_code_id}/download/?{urlencode(params)}"
    headers = {"Authorization": f"Token {token}"}
    resp = requests.get(url, headers=headers)
    check_response(resp, "2.2-download-qr-image")

    ext = canvas_type if canvas_type in ("pdf", "png", "svg") else "bin"
    out_path = os.path.join(output_dir, f"qr_{qr_code_id}.{ext}")
    with open(out_path, "wb") as f:
        f.write(resp.content)
    log.info("  Saved QR image → %s (%d bytes)", out_path, len(resp.content))
    return out_path


# ---------------------------------------------------------------------------
# Step 3 — Get S3 Signed URL for media upload
# ---------------------------------------------------------------------------
def get_signed_url(
    token: str, org_id: int, content_type: str = "application", folder: int = None
) -> dict:
    """
    POST /api/2.0/media/?organization={org_id}&content_type={content_type}
    Returns signed-URL details including presigned S3 POST fields.
    """
    log.info("━" * 60)
    log.info("STEP 3 — Get S3 Signed URL")
    params = {"organization": org_id, "content_type": content_type}
    url = f"{BASE_URL}/media/?{urlencode(params)}"
    payload = {
        "organization": org_id,
        "public": True,
        "typeform_compatible": None,
    }
    if folder is not None:
        payload["folder"] = folder
    resp = requests.post(url, headers=auth_headers(token), json=payload)
    check_response(resp, "3-get-signed-url")
    data = resp.json()

    # ── Debug: dump full response so we can see the actual structure ──
    log.info("  Full signed-URL response:\n%s", pretty(data))
    log.info("  Response top-level keys: %s", list(data.keys()))
    log.info("  Media ID    : %s", data.get("id"))
    return data


# ---------------------------------------------------------------------------
# Step 4 — Upload PDF to S3 using the signed URL
# ---------------------------------------------------------------------------
def upload_media_to_s3(signed_url_data: dict, pdf_path: str) -> requests.Response:
    """
    POST to the S3 bucket URL with the signed fields + file.
    The signed_url_data is the response from Step 3.
    The presigned fields (key, Policy, X-Amz-*) come from the Step 3 response,
    potentially nested under different keys depending on the API version.
    """
    log.info("━" * 60)
    log.info("STEP 4 — Upload Media to S3: %s", pdf_path)

    # Extract the S3 upload URL from the signed-URL response
    s3_url = (
        signed_url_data.get("post_action_url")
        or signed_url_data.get("upload_url")
        or signed_url_data.get("s3_url")
        or signed_url_data.get("url")
    )
    if not s3_url:
        raise ValueError(
            "Cannot upload: no S3 upload URL found in the media API response. "
            f"Response keys: {list(signed_url_data.keys())}"
        )
    log.info("  S3 Upload URL : %s", s3_url)

    # ── Extract presigned fields ──
    # The API may return them under "fields" (dict), "s3_fields" (dict),
    # or directly at the top level of the response.
    fields = (
        signed_url_data.get("fields")
        or signed_url_data.get("s3_fields")
        or signed_url_data.get("upload_fields")
        or {}
    )

    # The API returns presigned fields at the top level with lowercase
    # hyphenated names (e.g. "x-amz-algorithm", "policy").
    # Map from the API's key names to canonical S3 form field names.
    S3_FIELD_ALIASES = {
        "key": ["key"],
        "Policy": ["Policy", "policy"],
        "X-Amz-Algorithm": ["X-Amz-Algorithm", "x-amz-algorithm", "x_amz_algorithm"],
        "X-Amz-Credential": ["X-Amz-Credential", "x-amz-credential", "x_amz_credential"],
        "X-Amz-Date": ["X-Amz-Date", "x-amz-date", "x_amz_date"],
        "X-Amz-Signature": ["X-Amz-Signature", "x-amz-signature", "x_amz_signature"],
        "X-Amz-Security-Token": ["X-Amz-Security-Token", "x-amz-security-token", "x_amz_security_token"],
    }

    if not fields:
        # Fields are at the top level of the response
        log.info("  No nested 'fields' found — extracting from top-level keys")
        for canonical, aliases in S3_FIELD_ALIASES.items():
            for alias in aliases:
                if alias in signed_url_data:
                    fields[canonical] = signed_url_data[alias]
                    break

    log.info("  Presigned fields found: %s", list(fields.keys()))

    if not fields.get("key"):
        log.error(
            "  ❌ Could not find 'key' in signed URL response. "
            "Full response keys: %s\n"
            "Full response:\n%s",
            list(signed_url_data.keys()),
            pretty(signed_url_data),
        )
        raise ValueError(
            "Cannot upload: no presigned 'key' found in the media API response. "
            "Check the debug output above to see the actual response structure."
        )

    # Build multipart form in the order S3 expects
    form_fields = []
    # 'key' must come first in the S3 presigned POST
    form_fields.append(("key", (None, fields["key"])))
    for k, v in fields.items():
        if k == "key":
            continue
        form_fields.append((k, (None, str(v))))

    # Content-Type for the file
    form_fields.append(("Content-Type", (None, "application/pdf")))

    # The actual file — must be last
    pdf_filename = os.path.basename(pdf_path)
    form_fields.append(
        ("file", (pdf_filename, open(pdf_path, "rb"), "application/pdf"))
    )

    log.info("  Uploading %s to %s ...", pdf_filename, s3_url)
    resp = requests.post(s3_url, files=form_fields)
    # S3 returns 204 on success for presigned POST
    if resp.status_code in (200, 201, 204):
        log.info("  Upload ✓  Status: %s", resp.status_code)
    else:
        log.error("  Upload FAILED — %s\n%s", resp.status_code, resp.text[:2000])
        resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Step 4.1 — Verify Media Upload
# ---------------------------------------------------------------------------
def verify_media(token: str, org_id: int, media_id: int) -> dict:
    """
    GET /api/2.0/media/{media_id}/?organization={org_id}
    Checks the media record after S3 upload. Expected status: "Pending Upload".
    """
    log.info("━" * 60)
    log.info("STEP 4.1 — Verify Media Upload: media_id=%s", media_id)
    url = f"{BASE_URL}/media/{media_id}/?organization={org_id}"
    resp = requests.get(url, headers=auth_headers(token))
    check_response(resp, "4.1-verify-media")
    data = resp.json()
    log.info("  Status       : %s", data.get("status"))
    log.info("  S3 Object Key: %s", data.get("s3_object_key"))
    return data


# ---------------------------------------------------------------------------
# Step 4.2 — Activate Media Record
# ---------------------------------------------------------------------------
def activate_media(
    token: str, org_id: int, media_id: int, media_data: dict, pdf_name: str
) -> dict:
    """
    PUT /api/2.0/media/{media_id}/?organization={org_id}
    Transitions the media from "Pending Upload" → "Active" and sets name/content_type.
    """
    log.info("━" * 60)
    log.info("STEP 4.2 — Activate Media: media_id=%s", media_id)
    url = f"{BASE_URL}/media/{media_id}/?organization={org_id}"
    payload = {
        "id": media_id,
        "url": media_data.get("url", media_data.get("media_url", "")),
        "status": "Active",
        "name": pdf_name,
        "content_type": "application/pdf",
        "organization": org_id,
        "typeform_url": None,
        "typeform_compatible": False,
    }
    resp = requests.put(url, headers=auth_headers(token), json=payload)
    check_response(resp, "4.2-activate-media")
    data = resp.json()
    log.info("  Status       : %s", data.get("status"))
    log.info("  Name         : %s", data.get("name"))
    log.info("  Content-Type : %s", data.get("content_type"))
    return data


# ---------------------------------------------------------------------------
# Step 5 — Add PDF link to the Linkpage
# ---------------------------------------------------------------------------
def add_pdf_to_linkpage(
    token: str,
    org_id: int,
    linkpage_id: int,
    linkpage_url: str,
    pdf_url: str,
    pdf_name: str,
) -> dict:
    """
    PUT /api/2.0/linkpage/{linkpage_id}/?organization={org_id}
    Adds a link entry of url_type=10 (PDF) to the linkpage.
    """
    log.info("━" * 60)
    log.info("STEP 5 — Add PDF to Linkpage %s", linkpage_id)
    url = f"{BASE_URL}/linkpage/{linkpage_id}/?organization={org_id}"
    payload = {
        "links": [
            {
                "url_type": 10,
                "deleted": False,
                "url": "",
                "title": pdf_name,
                "image_type": 1,
                "image_url": "",
                "field_data": {
                    "pdf_url": pdf_url,
                    "pdf_name": pdf_name,
                },
            }
        ],
        "url": linkpage_url,
        "organization": org_id,
    }
    resp = requests.put(url, headers=auth_headers(token), json=payload)
    check_response(resp, "5-add-pdf-to-linkpage")

    # PUT response may not include links — re-fetch to verify
    get_resp = requests.get(url, headers=auth_headers(token))
    data = get_resp.json() if get_resp.ok else resp.json()
    links = data.get("links", [])
    log.info("  Links count : %s", len(links))
    for lnk in links:
        log.info("    Link ID=%s  type=%s  pdf_url=%s",
                 lnk.get("id"), lnk.get("url_type"),
                 lnk.get("field_data", {}).get("pdf_url", "N/A"))
    return data


# ---------------------------------------------------------------------------
# Step 6 — Delete PDF from Linkpage (optional)
# ---------------------------------------------------------------------------
def delete_pdf_from_linkpage(
    token: str,
    org_id: int,
    linkpage_id: int,
    linkpage_url: str,
    link_ids_to_delete: list[int],
) -> dict:
    """
    PUT /api/2.0/linkpage/{linkpage_id}/?organization={org_id}
    Sends deleted_links list to remove specific links.
    """
    log.info("━" * 60)
    log.info("STEP 6 — Delete PDF links %s from Linkpage %s", link_ids_to_delete, linkpage_id)
    url = f"{BASE_URL}/linkpage/{linkpage_id}/?organization={org_id}"
    payload = {
        "deleted_links": link_ids_to_delete,
        "links": [],
        "url": linkpage_url,
        "organization": org_id,
    }
    resp = requests.put(url, headers=auth_headers(token), json=payload)
    check_response(resp, "6-delete-pdf-from-linkpage")
    data = resp.json()
    log.info("  Remaining links : %s", len(data.get("links", [])))
    return data


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def run_flow(
    token: str,
    org_id: int,
    pdf_path: str,
    linkpage_name: str = "Hersheys TLC 101",
    qr_name: str = "QR: Hersheys 10001",
    media_folder: int = None,
    skip_delete: bool = True,
    output_dir: str = ".",
):
    """Execute the full flow, chaining outputs from each step."""
    results = {}

    # ── Step 1 ──
    linkpage = create_linkpage(token, org_id, linkpage_name)
    linkpage_id = linkpage["id"]
    linkpage_url = linkpage["url"]
    results["linkpage"] = linkpage

    # ── Step 2 ──
    qr = create_qr_code(token, org_id, linkpage_id, qr_name)
    qr_code_id = qr["id"]
    results["qr_code"] = qr

    # ── Step 2.1 ──
    qr_details = get_qr_details(token, qr_code_id)
    results["qr_details"] = qr_details

    # ── Step 2.2 ──
    qr_image_path = download_qr_image(token, qr_code_id, output_dir=output_dir)
    results["qr_image_path"] = qr_image_path

    # ── Step 3 ──
    signed_url_data = get_signed_url(
        token, org_id, content_type="application", folder=media_folder
    )
    results["signed_url"] = signed_url_data

    # Derive the pdf_url that the platform will serve after upload.
    # Pattern: {PDF_BASE_URL}/pdf/{media_id}
    # QA: https://q.eddy.pro/pdf/{id}  |  Production: https://eddy.pro/pdf/{id}
    media_id = signed_url_data.get("id")
    pdf_url = f"{PDF_BASE_URL}/pdf/{media_id}"
    log.info("  Resolved PDF URL : %s", pdf_url)

    # ── Step 4 ──
    upload_resp = upload_media_to_s3(signed_url_data, pdf_path)
    results["upload_status"] = upload_resp.status_code

    # ── Step 4.1 ──
    media_details = verify_media(token, org_id, media_id)
    results["media_details"] = media_details

    # ── Step 4.2 ──
    pdf_name = os.path.basename(pdf_path)
    activated_media = activate_media(
        token, org_id, media_id, media_details, pdf_name
    )
    results["activated_media"] = activated_media

    # ── Step 5 ──
    updated_linkpage = add_pdf_to_linkpage(
        token, org_id, linkpage_id, linkpage_url, pdf_url, pdf_name
    )
    results["updated_linkpage"] = updated_linkpage

    # ── Step 6 (optional) ──
    if not skip_delete:
        link_ids = [lnk["id"] for lnk in updated_linkpage.get("links", []) if "id" in lnk]
        if link_ids:
            delete_result = delete_pdf_from_linkpage(
                token, org_id, linkpage_id, linkpage_url, link_ids
            )
            results["delete_result"] = delete_result
        else:
            log.warning("  No link IDs found to delete — skipping Step 6")

    # ── Summary ──
    log.info("━" * 60)
    log.info("✅  FLOW COMPLETE")
    log.info("  Linkpage ID   : %s", linkpage_id)
    log.info("  Linkpage URL  : %s", linkpage_url)
    log.info("  QR Code ID    : %s", qr_code_id)
    log.info("  QR Image      : %s", qr_image_path)
    log.info("  PDF URL       : %s", pdf_url)
    log.info("━" * 60)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Run the Linkpages-as-PDF API flow end-to-end."
    )
    parser.add_argument(
        "--token",
        default=os.getenv("UNIQODE_TOKEN"),
        help="API auth token (or set UNIQODE_TOKEN env var)",
    )
    parser.add_argument(
        "--org-id",
        type=int,
        default=int(os.getenv("UNIQODE_ORG_ID", "0")),
        help="Organization ID (or set UNIQODE_ORG_ID env var)",
    )
    parser.add_argument(
        "--env",
        default=os.getenv("UNIQODE_ENV", "qa"),
        choices=["qa", "prod"],
        help="Target environment (or set UNIQODE_ENV env var). "
             "qa = QA/staging, prod = production",
    )
    parser.add_argument(
        "--pdf-path",
        required=True,
        help="Path to the PDF file to upload",
    )
    parser.add_argument(
        "--linkpage-name",
        default="Hersheys TLC 101",
        help="Name for the new linkpage",
    )
    parser.add_argument(
        "--qr-name",
        default="QR: Hersheys 10001",
        help="Name for the new QR code",
    )
    parser.add_argument(
        "--media-folder",
        type=int,
        default=None,
        help="Optional media folder ID for the S3 upload",
    )
    parser.add_argument(
        "--delete-after",
        action="store_true",
        help="Also run Step 6 (delete PDF from linkpage) after adding",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save downloaded QR image",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Apply environment config before any API calls
    global BASE_URL, PDF_BASE_URL
    env_cfg = ENV_CONFIG[args.env]
    BASE_URL = env_cfg["base_url"]
    PDF_BASE_URL = env_cfg["pdf_base_url"]
    log.info("Environment : %s", args.env)
    log.info("API base URL: %s", BASE_URL)
    log.info("PDF base URL: %s", PDF_BASE_URL)

    if not args.token:
        parser.error("--token is required (or set UNIQODE_TOKEN env var)")
    if not args.org_id:
        parser.error("--org-id is required (or set UNIQODE_ORG_ID env var)")
    if not Path(args.pdf_path).is_file():
        parser.error(f"PDF file not found: {args.pdf_path}")

    results = run_flow(
        token=args.token,
        org_id=args.org_id,
        pdf_path=args.pdf_path,
        linkpage_name=args.linkpage_name,
        qr_name=args.qr_name,
        media_folder=args.media_folder,
        skip_delete=not args.delete_after,
        output_dir=args.output_dir,
    )

    # Dump full results to JSON for debugging
    summary_path = os.path.join(args.output_dir, "flow_results.json")
    serializable = {
        k: v
        for k, v in results.items()
        if isinstance(v, (dict, list, str, int, float, bool, type(None)))
    }
    with open(summary_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    log.info("Full results saved → %s", summary_path)


if __name__ == "__main__":
    main()
