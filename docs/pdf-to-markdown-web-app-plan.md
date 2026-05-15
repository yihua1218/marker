# PDF to Markdown Web App Plan

Status note: this is a planning and implementation-history document. For current run, API, container, and integration instructions, start with [docs/README.md](./README.md).

## Goal

Build a small private web application that converts uploaded PDF files into Markdown using Marker, shows real-time conversion progress, and packages the generated Markdown plus extracted images for download.

The application source code may be public, but the hosted conversion service itself is intended to remain private, access-controlled, and limited to the maintainer's personal, non-commercial use.

The default output structure should place extracted images in an `images/` directory and keep the Markdown file at the root of the export package.

Example export layout:

```text
converted-document/
  document.md
  metadata.json
  images/
    page_0_picture_0.jpeg
    page_1_table_0.jpeg
```

## User Experience

The first MVP screen should be the actual converter, not a landing page.

Core flow:

1. The maintainer signs in through a private access gate.
2. The maintainer uploads one PDF.
3. The web app validates file type, size, and basic PDF readability.
4. The maintainer starts conversion.
5. A progress bar shows the current stage and percentage where available.
6. The app displays completion state, warnings, and output summary.
7. The maintainer downloads the result as `.zip`, `.tar.gz`, or another supported archive format.

Required UI elements:

- Private sign-in or VPN-only access gate.
- PDF upload control.
- Conversion settings panel with sensible defaults.
- Progress bar with stage labels such as `Queued`, `Loading models`, `Detecting layout`, `Recognizing text`, `Recognizing tables`, `Packaging output`, and `Complete`.
- Download format selector.
- Download button.
- Error panel for conversion failures.
- Footer or legal area with `Powered by Marker` and a link to the Marker GitHub repository: <https://github.com/VikParuchuri/marker>.

## Deployment Scope

This project should be implemented as a private personal tool:

- The source code can be published in a public repository.
- The running web service must not allow anonymous users, public registration, or third-party conversion access.
- Access should be limited to the maintainer through VPN, IP allowlist, single-user authentication, magic link, or another equivalent private access control.
- The service is intended only for personal, non-commercial document conversion by the maintainer.
- Uploaded PDFs, generated Markdown, extracted images, archives, secrets, API keys, model caches, and local job data must not be committed to the public source repository.
- Any future change that allows friends, coworkers, customers, public visitors, or automated external clients to use the hosted conversion service requires a new license review.

Suggested project notice:

```text
This private tool is powered by Marker and is intended only for the maintainer's personal, non-commercial document conversion use.
```

## Output And Archive Formats

Default options:

- Markdown filename: `document.md`, derived from the uploaded PDF name when safe.
- Image directory: `images/`.
- Metadata file: `metadata.json`.
- Default archive format: `.zip`.

Supported MVP archive formats:

- `.zip`
- `.tar.gz`

Possible later formats:

- `.tar`
- `.7z`, only if the server environment has a reliable and licensed implementation available.

The app should normalize paths before packaging to avoid unsafe filenames, path traversal, or accidental overwrites.

## Minimal MVP Execution Path

1. Add private access control before any upload or job endpoint is reachable.
2. Create a web server endpoint for PDF upload.
3. Store each uploaded PDF in a per-job temporary directory.
4. Create a conversion job record with status, progress, timestamps, input filename, output path, and error details.
5. Start a background worker process or task for the conversion.
6. Run Marker conversion against the uploaded PDF.
7. Copy or rewrite generated image references so the Markdown points to `images/<filename>`.
8. Move extracted images into the job's `images/` directory.
9. Create `metadata.json` with conversion settings, timing, Marker version, and warnings.
10. Build the selected archive format from the normalized output directory.
11. Expose progress polling or server-sent events so the browser can update the progress bar.
12. Show a completion screen with download links.
13. Clean temporary files after a retention period.

## Progress Reporting Strategy

Marker's CLI progress is currently emitted through logs and progress bars. For the MVP, use a pragmatic staged progress model:

- `0%`: job created.
- `5%`: upload validated.
- `10%`: worker started and models loading.
- `20%`: Marker conversion started.
- `35%`: layout detection stage observed or estimated.
- `55%`: text recognition stage observed or estimated.
- `75%`: table recognition or image extraction stage observed or estimated.
- `90%`: output normalization and archive packaging.
- `100%`: archive ready.

Implementation options:

- Prefer direct Python API integration for better control over output paths and metadata.
- If using the CLI first, capture subprocess output and map known log/progress messages to coarse progress stages.
- Keep the progress copy honest: use labels like `Working` or `Estimated progress` when exact percentage is not available.

## Architecture

Recommended MVP stack:

- Backend: FastAPI.
- Worker: local background task for MVP; move to Celery/RQ/Arq only when concurrent jobs require it.
- Frontend: simple server-rendered page or lightweight SPA.
- Storage: local filesystem under a configurable job directory.
- Packaging: Python standard library `zipfile` and `tarfile`.
- Container runtime: `nerdctl compose` with a Python runtime image and mounted persistent data.

Job directory layout:

```text
jobs/
  <job-id>/
    input/
      original.pdf
    output/
      document.md
      metadata.json
      images/
    archives/
      document.zip
      document.tar.gz
```

Containerized deployment files:

- `Dockerfile`: builds the frontend and packages the private Marker web service.
- `docker-compose.yml`: runs the service with `nerdctl compose`, maps the configured port, and persists `/app/data`.
- `.env.example`: documents runtime settings such as `PORT`, `MARKER_WEB_TOKEN`, `MARKER_WEB_JOB_DIR`, cache paths, image name, and image tag.
- `.env`: local ignored runtime configuration.

See [private-marker-container.md](./private-marker-container.md) for build, run, health check, and smoke-test commands.

## Security And Reliability

- Require authentication or VPN/IP allowlist before serving the converter.
- Disable public registration and anonymous access.
- Limit upload size.
- Accept only PDF MIME type and validate the file header.
- Generate server-side job IDs; never trust user-provided paths.
- Sanitize archive entry names.
- Run one conversion per job directory.
- Add conversion timeout controls.
- Surface partial warnings without exposing server stack traces.
- Clean old jobs on a schedule.
- Avoid storing documents permanently unless the product explicitly promises retention.
- Keep uploaded PDFs, outputs, archives, model caches, and secrets out of the public repository.

## Marker Attribution And Licensing Plan

Marker's repository declares the code license as `GPL-3.0-or-later` in `pyproject.toml`. The repository also includes `LICENSE`, which is GPL v3, and `README.md` states that the model weights use a modified AI Pubs OpenRAIL-M license.

The web app should handle licensing carefully:

- Display `Powered by Marker` in the UI with a visible link to <https://github.com/VikParuchuri/marker>.
- Include a `Licenses` page or modal that links to Marker, the GPL license text, and the model license text used by the deployed service.
- State that the hosted service is private, access-controlled, and intended only for the maintainer's personal, non-commercial use.
- Preserve Marker copyright, license, and attribution notices.
- If this app modifies Marker code or distributes a combined application that includes Marker, prepare to comply with GPL obligations, including providing corresponding source code under compatible terms where required.
- Publishing this app's source code is acceptable as a project goal, but the repository must not include private documents, generated outputs, secrets, model caches, or any files whose redistribution is not intended.
- If the app only runs Marker as a private server-side tool for the maintainer, still keep attribution clear and review GPL obligations before distributing any bundled application, container image, or modified Marker code.
- Do not imply endorsement by Marker, Datalab, Broadcom, or any upstream licensor.
- Follow the model license restrictions. The included `MODEL_LICENSE` has usage restrictions and attribution requirements, and the README states that broader commercial usage or removing GPL requirements requires a commercial license from Datalab.
- Do not allow third-party use of the hosted conversion service without a new license review.
- For public access, commercial self-hosting, enterprise use, coworkers, customers, or any case outside personal non-commercial use, consult counsel and review Datalab's commercial licensing page before launch.

This document is an implementation planning note, not legal advice.

## MVP Checklist

- [ ] Create `docs/` project notes for product, architecture, and licensing.
- [ ] Define the hosted service as private, personal, and non-commercial.
- [ ] Build a single-page upload UI.
- [ ] Add authentication, VPN-only routing, IP allowlist, or equivalent access control.
- [ ] Disable anonymous access and public registration.
- [ ] Add `Powered by Marker` with GitHub link.
- [ ] Add a `Licenses` link or modal.
- [ ] Implement PDF upload endpoint.
- [ ] Add upload size and PDF validation.
- [ ] Create job directory and job status model.
- [ ] Run Marker conversion in a background worker.
- [ ] Track staged progress for the progress bar.
- [ ] Normalize Markdown image references to `images/`.
- [ ] Move extracted images into `images/`.
- [ ] Write `metadata.json`.
- [ ] Package output as `.zip`.
- [ ] Package output as `.tar.gz`.
- [ ] Add archive format selector.
- [ ] Add download endpoint.
- [ ] Add failure state and readable error messages.
- [ ] Add job cleanup policy.
- [ ] Ensure uploaded PDFs, outputs, archives, secrets, and model caches are ignored by git.
- [ ] Add a container image build for the private web service.
- [ ] Add `nerdctl compose` runtime configuration.
- [ ] Document container build, run, health check, and smoke-test steps.
- [ ] Verify GPL and model-license compliance before distribution.
- [ ] Document that public access, third-party use, workplace use, customer use, or paid deployment requires a new licensing review.

## Later Enhancements

- Multiple PDF batch conversion.
- WebSocket or server-sent event progress updates.
- Queue dashboard for active jobs.
- Per-page preview.
- Markdown preview.
- Optional `use_llm` conversion mode with clear API key handling.
- Admin retention controls.
- Download audit logs for enterprise deployments.
