# Media ingestion foundation

Headline Avenue must distinguish between a source record and the actual source bytes.

## Current milestone

This branch adds real private binary ingestion for:

- video
- audio
- PDF

The upload endpoint stores the file and persists storage metadata in the authenticated workspace Source.

Uploaded media is deliberately marked `uploaded`, not `indexed`. A file is not editorially usable merely because its bytes exist. Video/audio require transcription; PDFs require text extraction. Those processing stages are the next layer.

## Storage modes

### Development

```text
MEDIA_STORAGE_BACKEND=local
MEDIA_LOCAL_DIR=./data/uploads
```

Files are stored privately below the backend working directory.

### Production

Use an S3-compatible private object store. Cloudflare R2 is the intended provider because the project already uses Cloudflare for DNS.

```text
MEDIA_STORAGE_BACKEND=r2
MEDIA_S3_ENDPOINT_URL=<S3-compatible endpoint>
MEDIA_S3_BUCKET=<private bucket>
MEDIA_S3_ACCESS_KEY_ID=<bucket-scoped credential>
MEDIA_S3_SECRET_ACCESS_KEY=<bucket-scoped credential>
MEDIA_S3_REGION=auto
```

Do not make the bucket public. Publishing/rendering should use controlled backend access or short-lived signed URLs later.

## Source state contract

- `uploaded`: binary bytes are safely stored but not yet transcribed/extracted.
- `indexed`: readable source text is available for story intelligence.
- `needs_review` / `needs_content`: editorial or ingestion intervention is required.
- `upload_failed`: storage failed and the source cannot be used.

This state distinction prevents the UI from claiming that an uploaded file has been analyzed when it has not.

## Next layer

1. transcription/extraction job model
2. asynchronous worker
3. audio/video transcription with timestamps
4. PDF text extraction
5. update Source to `indexed`
6. enable Story creation from processed media


## Speech-to-text provider

The current provider is Deepgram Nova-3 because Headline Avenue needs timestamped, speaker-aware transcripts for interview and video workflows.

Configuration:

```text
TRANSCRIPTION_PROVIDER=deepgram
DEEPGRAM_API_KEY=<secret>
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=multi
DEEPGRAM_DIARIZE=true
```

Do not expose the API key in frontend JavaScript. It belongs only in the backend/worker environment.

The browser does not call the provider directly. The flow is:

```text
POST /sources/{id}/transcribe
  -> ingestion_jobs.status = queued
  -> worker claims job
  -> Source.status = transcribing
  -> private media is sent to provider
  -> transcript_text + timestamped speaker segments are persisted
  -> Source.status = indexed
  -> Story creation becomes available
```

## Transcript storage

The full readable transcript remains on `sources.transcript_text`.

Timestamped units are stored separately in `source_transcript_segments`:

- sequence
- start_ms
- end_ms
- speaker
- text
- confidence

This avoids returning a huge timestamp payload every time the Source row is loaded while preserving the evidence trail needed for clip selection and later subtitle work.

## Worker deployment

Local development starts `python -m app.ingestion_worker` in a separate PowerShell window.

Production should run the same module as a separate Railway worker service against the same PostgreSQL database and private object-storage credentials. The web API only queues jobs; it should not perform long transcription calls inside request handlers.
