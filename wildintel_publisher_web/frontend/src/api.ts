import type { BrowseResult, ClassificationProject, DatapackageSummary, Deployment, OutputMode, ResearchProject } from './types'

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
  ) =>
    post<{ task_id: string }>('/api/trapper/download', {
      url, username, password, project_id: projectId, deployment_id: deploymentId,
    }),

  trapperDownloadStatus: (taskId: string) =>
    req<{ status: 'running' | 'done' | 'error'; path: string | null; error: string | null }>(
      `/api/trapper/download/${taskId}`,
    ),

  softwareCloneStart: (url: string, clearCache = false) =>
    post<{ task_id: string }>('/api/software/clone', { url, clear_cache: clearCache }),

  softwareCloneStatus: (taskId: string) =>
    req<{ status: 'running' | 'done' | 'error'; path: string | null; error: string | null }>(
      `/api/software/clone/${taskId}`,
    ),

  camtrapdpFetchArchiveStart: (url: string, clearCache = false) =>
    post<{ task_id: string }>('/api/camtrapdp/fetch-archive', { url, clear_cache: clearCache }),

  camtrapdpFetchArchiveStatus: (taskId: string) =>
    req<{ status: 'running' | 'done' | 'error'; path: string | null; error: string | null }>(
      `/api/camtrapdp/fetch-archive/${taskId}`,
    ),

  generateProductMetadata: (inputDir: string, productType: string) =>
    post<DatapackageSummary>('/api/camtrapdp/generate-metadata', { input_dir: inputDir, product_type: productType }),

  completeProductMetadata: (inputDir: string, updates: Partial<Omit<DatapackageSummary, 'product_type' | 'hfh_repo_id'>>) =>
    post<DatapackageSummary>('/api/camtrapdp/complete-metadata', { input_dir: inputDir, ...updates }),

  datapackageSummary: (path: string) =>
    req<DatapackageSummary>(`/api/camtrapdp/summary?path=${encodeURIComponent(path)}`),

  datapackageDownloadUrl: (path: string) =>
    `/api/camtrapdp/download?path=${encodeURIComponent(path)}`,

  openFolder: (path: string) =>
    post<{ ok: boolean }>('/api/camtrapdp/open-folder', { path }),

  fsBrowse: (path?: string) =>
    req<BrowseResult>(`/api/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`),

  hfhGetConfig: () =>
    req<{ username: string | null; output_dir: string; version: string; timeout: number; has_token: boolean }>(
      '/api/hfh/config',
    ),

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

  gbifValidateArchive: (archiveUrl: string) =>
    post<{ ok: boolean }>('/api/gbif/validate-archive', { archive_url: archiveUrl }),

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
    version?: string
    timeout?: number
    primaryDoiSource?: 'zenodo' | 'b2share'
    // If true, nothing is actually uploaded/created/released anywhere —
    // Zenodo/B2SHARE's DOI reservation is simulated instead, so the DOI
    // cross-referencing step still has something real to work with. No
    // token/repo_id/community_id is required in this mode.
    dryRun?: boolean
    repos: Array<{
      repo: 'hfh' | 'zenodo' | 'b2share' | 'gbif'
      outputDir: string
      token?: string
      mirrorImages: boolean
      outputMode: OutputMode
      repoId?: string
      private?: boolean
      environment?: string
      communities?: string
      communityId?: string
      // gbif-only
      archiveUrl?: string
      publishingOrganizationKey?: string
      installationKey?: string
      registryLanguage?: string
      username?: string
      password?: string
    }>
  }) =>
    post<{ task_id: string }>('/api/publish/start', {
      input_dir: params.inputDir,
      version: params.version,
      timeout: params.timeout,
      primary_doi_source: params.primaryDoiSource,
      dry_run: params.dryRun ?? false,
      repos: params.repos.map((r) => ({
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
        archive_url: r.archiveUrl,
        publishing_organization_key: r.publishingOrganizationKey,
        installation_key: r.installationKey,
        registry_language: r.registryLanguage,
        username: r.username,
        password: r.password,
      })),
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
}
