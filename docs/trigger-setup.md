# Reliable 15-minute trigger (cron-job.org -> GitHub Actions)

GitHub's own `schedule:` cron is best-effort and silently skipped most slots on
this repo. This setup makes an external free service call the workflow's
`workflow_dispatch` endpoint every 15 minutes. The built-in cron stays as a
backup, and the workflow's `concurrency` group guarantees two scans never run
at once, so a double trigger is harmless.

## 1. Create a GitHub token (only you can do this)

1. GitHub -> Settings -> Developer settings -> Personal access tokens ->
   **Fine-grained tokens** -> Generate new token.
2. Resource owner: your account. **Repository access: Only select repositories**
   -> `offer_hunter`.
3. Permissions -> Repository permissions -> **Actions: Read and write**
   (Metadata: Read is added automatically). Nothing else.
4. Expiration: 1 year (set a reminder; when it expires the trigger stops and
   cron-job.org will email you).
5. Copy the token (`github_pat_...`). Never paste it in chat or commit it.

## 2. Create the job on cron-job.org

1. Sign up at https://cron-job.org (free).
2. **Create cronjob**
   - Title: `offer_hunter scan`
   - URL: `https://api.github.com/repos/felipe12012/offer_hunter/actions/workflows/fast.yml/dispatches`
   - Schedule: every 15 minutes.
3. **Advanced** tab
   - Request method: `POST`
   - Request body: `{"ref":"main"}`
   - Headers (add each):
     - `Authorization`: `Bearer github_pat_xxxxxxxx`
     - `Accept`: `application/vnd.github+json`
     - `X-GitHub-Api-Version`: `2022-11-28`
     - `Content-Type`: `application/json`
     - `User-Agent`: `cron-job.org`
4. Enable **notification on failure** so an expired token is noticed.
5. Save, then use **Test run**: the expected response is **HTTP 204**.

## 3. Verify

After a few minutes the Actions tab should show runs with event
`workflow_dispatch` roughly every 15 minutes:

```
gh run list -R felipe12012/offer_hunter --event workflow_dispatch --limit 10
```

Common errors: `401` token wrong/expired, `403`/`404` token lacks Actions
write access or is not scoped to this repository, `422` wrong workflow file
name or `ref`.
