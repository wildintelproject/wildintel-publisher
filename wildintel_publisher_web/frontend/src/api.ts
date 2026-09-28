import type {
  AppSettings, AppSettingsUpdate,
  BrowseResult, Organization, ClassificationProject, DatapackageFields, DatapackageSummary, Deployment,
  YoloDataYamlFields, YoloDataYamlMetadata, PreviousVersion,
  GBIFInstallation, OutputMode, PublishRepoConfig, ResearchProject, SessionSummary,
} from './types'

async function req<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch(url, options)
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    let message = text
    try { message = JSON.parse(text).detail ?? text } catch { /* not JSON */ }
    throw new Error(message)
  }
  return r.json() as Promise<T>
}

function post<T>(url: string, body: unknown): Promise<T> {
  return req<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function put<T>(url: string, body: unknown): Promise<T> {
  return req<T>(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export const api = {
  checkHealth: async (): Promise<boolean> => {
    try {
      const r = await fetch('/api/health')
      return r.ok
    } catch {
      return false
    }
  },

  checkVersion: () =>
    req<{ current: string; latest: string | null; update_available: boolean; release_url: string | null }>('/api/version'),

  getSettings: () => req<AppSettings>('/api/settings'),
  saveSettings: (update: AppSettingsUpdate) => put<AppSettings>('/api/settings', update),

  trapperGetConfig: () =>
    req<{ base_url: string | null; user_name: string | null; has_password: boolean }>('/api/trapper/config'),

  trapperTestConnection: (url: string, username: string, password: string) =>
    post<{ ok: boolean; research_projects_count: number }>('/api/trapper/test-connection', { url, username, password }),

  trapperResearchProjects: (url: string, username: string, password: string) =>
    post<{ results: ResearchProject[] }>('/api/trapper/research-projects', { url, username, password }),

  trapperClassificationProjects: (url: string, username: string, password: string, researchProjectPk: number) =>
    post<{ results: ClassificationProject[] }>('/api/trapper/classification-projects', {
      url, username, password, research_project_pk: researchProjectPk,
    }),

  trapperDeployments: (url: string, username: string, password: string, classificationProjectPk: number) =>
    post<{ results: Deployment[] }>('/api/trapper/deployments', {
      url, username, password, classification_project_pk: classificationProjectPk,
    }),

  trapperStartDownload: (
    url: string, username: string, password: string, projectId: number, deploymentId: string,
    includeEvents = true,
  ) =>
    post<{ task_id: string }>('/api/trapper/download', {
      url, username, password, project_id: projectId, deployment_id: deploymentId,
      include_events: includeEvents,
    }),

  trapperDownloadStatus: (taskId: string) =>
    req<{ status: 'running' | 'done' | 'error'; path: string | null; error: string | null }>(
      `/api/trapper/download/${taskId}`,
    ),

  // Resumes a Trapper fetch an earlier interruption left on disk — same
  // project/deployment as the original request (persisted server-side);
  // only credentials need to be re-entered (never saved to disk).
  trapperResumeDownload: (taskId: string, url: string, username: string, password: string) =>
    post<{ task_id: string }>(`/api/trapper/download/${taskId}/resume`, { url, username, password }),

  softwareCloneStart: (url: string, clearCache = false) =>
    post<{ task_id: string }>('/api/software/clone', { url, clear_cache: clearCache }),

  softwareCloneStatus: (taskId: string) =>
    req<{ status: 'running' | 'done' | 'error'; path: string | null; error: string | null }>(
      `/api/software/clone/${taskId}`,
    ),

  // Resumes a git clone an earlier interruption left on disk — same url as
  // the original request; no credentials involved.
  softwareResumeClone: (taskId: string) =>
    post<{ task_id: string }>(`/api/software/clone/${taskId}/resume`, {}),

  camtrapdpFetchArchiveStart: (url: string, clearCache = false) =>
    post<{ task_id: string }>('/api/camtrapdp/fetch-archive', { url, clear_cache: clearCache }),

  camtrapdpFetchArchiveStatus: (taskId: string) =>
    req<{ status: 'running' | 'done' | 'error'; path: string | null; error: string | null }>(
      `/api/camtrapdp/fetch-archive/${taskId}`,
    ),

  // Resumes a public-URL fetch an earlier interruption left on disk — same
  // url as the original request; no credentials involved.
  camtrapdpResumeFetchArchive: (taskId: string) =>
    post<{ task_id: string }>(`/api/camtrapdp/fetch-archive/${taskId}/resume`, {}),

  // Copies path's core Camtrap DP files (datapackage.json + its 3 tables —
  // never any media) into an app-owned working directory (inside a
  // session — see services.session_store) and validates it. Synchronous,
  // unlike fetch-archive/Trapper's download above: it's just a few small
  // local files, not a network fetch. workingDir is what the rest of the
  // wizard should use as input_dir from here on; sourceDir (== path) is
  // kept only so media.csv's locally-referenced images can still be found
  // later, at the actual publish step (see mediaDir in publishAllStart
  // below) — never copied here. taskId is that session's own task_id,
  // present even on failure — pass it back in as sessionTaskId on every
  // later call for this same form (see LocalDirectoryForm's own debounced
  // live-preview) so a path edit reuses the same session_dir instead of
  // minting a new one per keystroke, and thread it into
  // generateProductMetadata/publishAllStart below exactly like a Trapper/
  // git/archive session's own task_id.
  resolveLocalSource: (path: string, sessionTaskId?: string) =>
    post<{ status: 'valid' | 'invalid'; workingDir: string | null; sourceDir: string; taskId: string; error: string | null }>(
      '/api/camtrapdp/resolve-local-source', { path, session_task_id: sessionTaskId },
    ),

  // anonymizeCoordinates/coordinateDecimals (Camtrap DP only) round
  // deployments.csv's latitude/longitude in inputDir itself, once, here —
  // see WizardPage's anonymizeCoordinates/coordinateDecimals state.
  // randomizeMediaIds (Camtrap DP only) replaces every mediaID that isn't
  // already a UUID with one derived from mediaIdDomain, same "applied once
  // here" shape — see WizardPage's mediaIdDomain state.
  // sessionTaskId (the session a prior Trapper/git/archive fetch, or a
  // Local Directory resolve, already started — see WizardPage's own
  // sessionTaskId state) flips that session's phase to "preprocessing"/
  // "preprocessed" server-side; undefined only for a request that
  // predates this feature.
  generateProductMetadata: (
    inputDir: string, productType: string,
    anonymizeCoordinates = false, coordinateDecimals = 2, randomizeMediaIds = false,
    mediaIdDomain = 'localhost', sessionTaskId?: string,
  ) =>
    post<DatapackageSummary>('/api/camtrapdp/generate-metadata', {
      input_dir: inputDir, product_type: productType,
      anonymize_coordinates: anonymizeCoordinates, coordinate_decimals: coordinateDecimals,
      randomize_media_ids: randomizeMediaIds, media_id_domain: mediaIdDomain,
      session_task_id: sessionTaskId,
    }),

  completeProductMetadata: (inputDir: string, updates: Partial<Omit<DatapackageSummary, 'product_type' | 'hfh_repo_id'>>) =>
    post<DatapackageSummary>('/api/camtrapdp/complete-metadata', { input_dir: inputDir, ...updates }),

  // Camtrap DP only — reads/patches datapackage.json ITSELF (not
  // metadata.json, see generateProductMetadata/completeProductMetadata
  // above). datapackageFields works even before generateProductMetadata
  // has ever run (no metadata.json needed yet), so the wizard's new
  // metadata-editing step can pre-fill its form right after the source is
  // downloaded/resolved. updateDatapackageFields is meant to be called
  // BEFORE generateProductMetadata: CamtrapDPAdapter.extract_metadata
  // re-reads these same fields from datapackage.json every time it runs,
  // so patching first is enough for metadata.json (and everything
  // generated from it) to pick up the new values, with no separate write.
  datapackageFields: (path: string) =>
    req<DatapackageFields>(`/api/camtrapdp/datapackage-fields?path=${encodeURIComponent(path)}`),

  updateDatapackageFields: (inputDir: string, updates: DatapackageFields) =>
    post<{ ok: boolean }>('/api/camtrapdp/update-datapackage', { input_dir: inputDir, ...updates }),

  // YOLO only — same contract as resolveLocalSource above, except the
  // working copy holds just data.yaml (plus a pointer back to path for
  // images/labels, never copied). yoloDataYamlFields/updateYoloDataYaml are
  // YOLO's counterpart of datapackageFields/updateDatapackageFields: the
  // metadata keys this tool adds to data.yaml, edited on the working copy
  // BEFORE generateProductMetadata, which re-reads them from there.
  yoloResolveLocalSource: (path: string, sessionTaskId?: string) =>
    post<{ status: 'valid' | 'invalid'; workingDir: string | null; sourceDir: string; taskId: string; error: string | null }>(
      '/api/yolo/resolve-local-source', { path, session_task_id: sessionTaskId },
    ),

  yoloDataYamlFields: (path: string) =>
    req<YoloDataYamlFields>(`/api/yolo/data-yaml-fields?path=${encodeURIComponent(path)}`),

  updateYoloDataYaml: (inputDir: string, fields: YoloDataYamlMetadata) =>
    post<{ ok: boolean }>('/api/yolo/update-data-yaml', { input_dir: inputDir, ...fields }),

  datapackageSummary: (path: string) =>
    req<DatapackageSummary>(`/api/camtrapdp/summary?path=${encodeURIComponent(path)}`),

  datapackageDownloadUrl: (path: string) =>
    `/api/camtrapdp/download?path=${encodeURIComponent(path)}`,

  // settings.toml's own PRODUCT.organizations, shared by every product type (see
  // wildintel_publisher.config.ProductSettings), offered as the
  // selectable options for BOTH the "publisher" and "rightsHolder"
  // contributor roles in WizardPage's metadata-editing step. Hand-edit
  // settings.toml's own [[PRODUCT.organizations]] to add/remove one —
  // no frontend code change needed.
  organizations: () => req<Organization[]>('/api/product/organizations'),

  openFolder: (path: string) =>
    post<{ ok: boolean }>('/api/camtrapdp/open-folder', { path }),

  fsBrowse: (path?: string) =>
    req<BrowseResult>(`/api/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`),

  hfhGetConfig: () =>
    req<{ username: string | null; output_dir: string; version: string; timeout: number; has_token: boolean }>(
      '/api/hfh/config',
    ),

  // Whether this Hugging Face Hub dataset already exists — the HFH form
  // warns when a "new dataset" would publish on top of it.
  // The saved token's own datasets (its user's and organizations') — the
  // "new version" picker's list (see PublicationKindPicker).
  hfhDatasets: () => req<{ id: string; title: string; version?: string | null; published?: string | null }[]>('/api/hfh/datasets'),

  hfhRepoExists: (repoId: string) =>
    req<{ exists: boolean }>(`/api/hfh/repo-exists?repo_id=${encodeURIComponent(repoId)}`),

  // The previous version of an already-published dataset, found on every
  // repository reachable from one identifier (a HFH repo_id, a Zenodo/
  // B2SHARE record id, or any of their URLs/DOIs) — see
  // services.previous_version_service.
  previousVersion: (repo: 'hfh' | 'zenodo' | 'b2share' | 'gbif', identifier: string) =>
    post<PreviousVersion>('/api/publish/previous-version', { repo, identifier }),

  hfhTestToken: (repoId: string, token: string, version?: string) =>
    post<{ ok: boolean; username: string; version_conflict: boolean }>(
      '/api/hfh/test-token', { repo_id: repoId, token, version },
    ),

  hfhStartPublish: (params: {
    inputDir: string
    outputDir: string
    timeout: number
    repoId: string
    private: boolean
    token: string
    mirrorImages: boolean
    outputMode: OutputMode
  }) =>
    // No "version" here: metadata.json already has one (the wizard requires
    // it to be filled in before Step 3 — see missingRequiredFields), and the
    // backend always prefers it over anything else.
    post<{ task_id: string }>('/api/hfh/publish', {
      input_dir: params.inputDir,
      output_dir: params.outputDir,
      timeout: params.timeout,
      repo_id: params.repoId,
      private: params.private,
      token: params.token,
      mirror_images: params.mirrorImages,
      output_mode: params.outputMode,
    }),

  hfhPublishStatus: (taskId: string) =>
    req<{
      status: 'running' | 'done' | 'error'
      stage: string
      repo_url: string | null
      output_dir: string | null
      error: string | null
    }>(`/api/hfh/publish/${taskId}`),

  zenodoGetConfig: () =>
    req<{
      environment: 'sandbox' | 'production'
      communities: string | null
      output_dir: string
      version: string
      timeout: number
      has_token: boolean
    }>('/api/zenodo/config'),

  zenodoTestToken: (token: string, environment: string) =>
    post<{ ok: boolean }>('/api/zenodo/test-token', { token, environment }),

  zenodoStartPublish: (params: {
    inputDir: string
    outputDir: string
    timeout: number
    mirrorImages: boolean
    hfhRepoId: string
    environment: string
    communities: string
    token: string
    outputMode: OutputMode
  }) =>
    // No "version" here: metadata.json already has one (the wizard requires
    // it to be filled in before Step 3 — see missingRequiredFields), and the
    // backend always prefers it over anything else.
    post<{ task_id: string }>('/api/zenodo/publish', {
      input_dir: params.inputDir,
      output_dir: params.outputDir,
      timeout: params.timeout,
      mirror_images: params.mirrorImages,
      hfh_repo_id: params.hfhRepoId || null,
      environment: params.environment,
      communities: params.communities || null,
      token: params.token,
      output_mode: params.outputMode,
    }),

  zenodoPublishStatus: (taskId: string) =>
    req<{
      status: 'running' | 'done' | 'error'
      stage: string
      doi: string | null
      record_url: string | null
      output_dir: string | null
      error: string | null
    }>(`/api/zenodo/publish/${taskId}`),

  // Published depositions belonging to the caller's own token, on
  // `environment` — ZenodoPublishForm's own "Search existing depositions"
  // button, so the user can pick an existingDepositionId instead of typing/
  // tracking a numeric id by hand. Unlike GBIF's public Registry search (by
  // organization), Zenodo's deposit API is always scoped to the token.
  zenodoDepositions: (environment: string, token: string, query?: string) =>
    post<{ id: string; title: string; version?: string | null; published?: string | null }[]>('/api/zenodo/depositions', { environment, token: token || null, query: query || null }),

  zenodoSyncDoi: (params: { zenodoOutputDir: string; hfhOutputDir: string; hfhRepoId: string; hfhToken: string }) =>
    post<{ doi: string; repo_url: string }>('/api/zenodo/sync-doi', {
      zenodo_output_dir: params.zenodoOutputDir,
      hfh_output_dir: params.hfhOutputDir,
      hfh_repo_id: params.hfhRepoId,
      hfh_token: params.hfhToken,
    }),

  b2shareGetConfig: () =>
    req<{
      environment: 'sandbox' | 'production'
      community_id: string | null
      output_dir: string
      version: string
      timeout: number
      has_token: boolean
    }>('/api/b2share/config'),

  b2shareTestToken: (token: string, environment: string) =>
    post<{ ok: boolean }>('/api/b2share/test-token', { token, environment }),

  b2shareStartPublish: (params: {
    inputDir: string
    outputDir: string
    timeout: number
    mirrorImages: boolean
    hfhRepoId: string
    environment: string
    communityId: string
    token: string
    outputMode: OutputMode
  }) =>
    // No "version" here: metadata.json already has one (the wizard requires
    // it to be filled in before Step 3 — see missingRequiredFields), and the
    // backend always prefers it over anything else.
    post<{ task_id: string }>('/api/b2share/publish', {
      input_dir: params.inputDir,
      output_dir: params.outputDir,
      timeout: params.timeout,
      mirror_images: params.mirrorImages,
      hfh_repo_id: params.hfhRepoId || null,
      environment: params.environment,
      community_id: params.communityId || null,
      token: params.token,
      output_mode: params.outputMode,
    }),

  b2sharePublishStatus: (taskId: string) =>
    req<{
      status: 'running' | 'done' | 'error'
      stage: string
      pid: string | null
      record_url: string | null
      output_dir: string | null
      error: string | null
    }>(`/api/b2share/publish/${taskId}`),

  // Published records belonging to the caller's own token, on
  // `environment` — B2SharePublishForm's own "Search existing records"
  // button, so the user can pick an existingRecordId instead of typing/
  // tracking one by hand. Unlike GBIF's public Registry search (by
  // organization), B2SHARE's (InvenioRDM) user-records API is always
  // scoped to the token.
  b2shareRecords: (environment: string, token: string, query?: string) =>
    post<{ id: string; title: string; version?: string | null; published?: string | null }[]>('/api/b2share/records', { environment, token: token || null, query: query || null }),

  b2shareSyncPid: (params: { b2shareOutputDir: string; hfhOutputDir: string; hfhRepoId: string; hfhToken: string }) =>
    post<{ pid: string | null; repo_url: string }>('/api/b2share/sync-pid', {
      b2share_output_dir: params.b2shareOutputDir,
      hfh_output_dir: params.hfhOutputDir,
      hfh_repo_id: params.hfhRepoId,
      hfh_token: params.hfhToken,
    }),

  gbifGetConfig: () =>
    req<{
      environment: 'sandbox' | 'production'
      publishing_organization_key: string | null
      installation_key: string | null
      registry_language: string | null
      output_dir: string
      has_credentials: boolean
    }>('/api/gbif/config'),

  gbifTestCredentials: (username: string, password: string, environment: string) =>
    post<{ ok: boolean }>('/api/gbif/test-credentials', { username, password, environment }),

  // settings.toml's own GBIF.installations — GBIFPublishForm's own
  // "Installation UUID" quick-fill dropdown, same idea as
  // organizations but for a GBIF installation (a distinct GBIF
  // concept, no Camtrap DP equivalent) instead of an organization.
  gbifInstallations: () => req<GBIFInstallation[]>('/api/gbif/installations'),

  gbifValidateArchive: (archiveUrl: string) =>
    post<{ ok: boolean }>('/api/gbif/validate-archive', { archive_url: archiveUrl }),

  // Datasets already published by organizationKey on `environment`
  // (sandbox/production) — GBIFPublishForm's own "search existing
  // datasets" button, so the user can pick a dataset_key instead of
  // typing/tracking a UUID by hand. A public GBIF Registry read; no
  // credentials involved.
  gbifOrganizationDatasets: (organizationKey: string, environment: string) =>
    post<{ key: string; title: string; published?: string | null }[]>('/api/gbif/organization-datasets', {
      organization_key: organizationKey, environment,
    }),

  gbifSyncDoi: (params: { gbifOutputDir: string; hfhOutputDir: string; hfhRepoId: string; hfhToken: string }) =>
    post<{ doi: string; repo_url: string }>('/api/gbif/sync-doi', {
      gbif_output_dir: params.gbifOutputDir,
      hfh_output_dir: params.hfhOutputDir,
      hfh_repo_id: params.hfhRepoId,
      hfh_token: params.hfhToken,
    }),

  // Publishes every selected repo in one go: upload phase for all of them,
  // then a cross-repo DOI populate pass, then release/lock for all of them
  // (see the backend's services.publish_orchestrator/doi_populate) — the
  // wizard no longer sequences each repo's own start/poll cycle itself.
  publishAllStart: (params: {
    inputDir: string
    // Where locally-referenced media (media.csv's filePath, non-URL
    // entries) actually lives — only different from inputDir for a local
    // Camtrap DP source, where inputDir is a working copy of just the core
    // files (see resolveLocalSource above) and the real media stayed at
    // this original path. Undefined/omitted for every other source type.
    mediaDir?: string
    version?: string
    timeout?: number
    primaryDoiSource?: 'zenodo' | 'b2share'
    // If true, nothing is actually uploaded/created/released anywhere —
    // Zenodo/B2SHARE's DOI reservation is simulated instead, so the DOI
    // cross-referencing step still has something real to work with. No
    // token/repo_id/community_id is required in this mode.
    dryRun?: boolean
    repos: PublishRepoConfig[]
    // The session a prior Trapper/git/archive fetch, or a Local Directory
    // resolve, (and, usually, preprocessing) already started — see
    // WizardPage's own sessionTaskId state. When given, the backend reuses
    // that exact session instead of minting a new one, so the fetched
    // source/preprocessing choices and this publish's own build dirs all
    // end up under the same folder. Undefined only for a request that
    // predates this feature.
    sessionTaskId?: string
  }) =>
    post<{ task_id: string }>('/api/publish/start', {
      input_dir: params.inputDir,
      media_dir: params.mediaDir || null,
      version: params.version,
      timeout: params.timeout,
      primary_doi_source: params.primaryDoiSource,
      dry_run: params.dryRun ?? false,
      repos: params.repos.map(_repoConfigToApi),
      session_task_id: params.sessionTaskId,
    }),

  publishAllStatus: (taskId: string) =>
    req<{
      status: 'running' | 'done' | 'error'
      error: string | null
      dry_run: boolean
      repos: Record<string, {
        status: 'pending' | 'running' | 'done' | 'error'
        stage: string
        error: string | null
        repo_url: string | null
        doi: string | null
        pid: string | null
        output_dir: string | null
        doi_synced_to_hfh?: boolean | null
      }>
    }>(`/api/publish/${taskId}`),

  // Sessions an earlier interruption left on disk, at ANY phase (fetching a
  // source, preprocessing it, or publishing — see services.session_store) —
  // offered on web app startup so the user can resume or discard instead of
  // starting over. Never carries credentials (see SessionSummary's own
  // docstring).
  listPublishSessions: () => req<SessionSummary[]>('/api/publish/sessions'),

  // Resumes an interrupted session — same repos/order as the original run,
  // with freshly-supplied credentials (never persisted, so always required
  // again here). Already-finished repos, already-downloaded images, and
  // (for Zenodo/B2SHARE) already-uploaded files are skipped server-side.
  resumePublishStart: (taskId: string, repos: PublishRepoConfig[], version?: string, timeout?: number) =>
    post<{ task_id: string }>(`/api/publish/sessions/${taskId}/resume`, {
      repos: repos.map(_repoConfigToApi),
      version,
      timeout,
    }),

  // Permanently discards an interrupted session instead of resuming it.
  discardPublishSession: (taskId: string) =>
    req<{ status: string }>(`/api/publish/sessions/${taskId}`, { method: 'DELETE' }),
}

function _repoConfigToApi(r: PublishRepoConfig) {
  return {
    repo: r.repo,
    output_dir: r.outputDir,
    token: r.token,
    mirror_images: r.mirrorImages,
    output_mode: r.outputMode,
    repo_id: r.repoId,
    private: r.private,
    environment: r.environment,
    communities: r.communities,
    community_id: r.communityId,
    existing_deposition_id: r.existingDepositionId,
    existing_record_id: r.existingRecordId,
    fit_archive_size: r.fitArchiveSize,
    max_zip_file: r.maxZipFile,
    min_image_edge: r.minImageEdge,
    archive_url: r.archiveUrl,
    publishing_organization_key: r.publishingOrganizationKey,
    installation_key: r.installationKey,
    registry_language: r.registryLanguage,
    username: r.username,
    password: r.password,
    dataset_key: r.datasetKey,
  }
}
