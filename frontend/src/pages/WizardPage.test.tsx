import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import type { PreprocessingSession, PublishSessionSummary } from '../types'
import WizardPage from './WizardPage'

vi.mock('../api', () => ({
  api: {
    trapperGetConfig: vi.fn(),
    trapperTestConnection: vi.fn(),
    trapperResearchProjects: vi.fn(),
    trapperClassificationProjects: vi.fn(),
    trapperDeployments: vi.fn(),
    trapperStartDownload: vi.fn(),
    trapperDownloadStatus: vi.fn(),
    softwareCloneStart: vi.fn(),
    softwareCloneStatus: vi.fn(),
    camtrapdpFetchArchiveStart: vi.fn(),
    camtrapdpFetchArchiveStatus: vi.fn(),
    resolveLocalSource: vi.fn(),
    yoloResolveLocalSource: vi.fn(),
    yoloDataYamlFields: vi.fn(),
    updateYoloDataYaml: vi.fn(),
    previousVersion: vi.fn(),
    hfhRepoExists: vi.fn(),
    hfhDatasets: vi.fn(),
    zenodoDepositions: vi.fn(),
    generateProductMetadata: vi.fn(),
    completeProductMetadata: vi.fn(),
    datapackageFields: vi.fn(),
    updateDatapackageFields: vi.fn(),
    datapackageSummary: vi.fn(),
    organizations: vi.fn(),
    datapackageDownloadUrl: vi.fn((path: string) => `/api/camtrapdp/download?path=${path}`),
    openFolder: vi.fn(),
    fsBrowse: vi.fn(),
    hfhGetConfig: vi.fn(),
    hfhTestToken: vi.fn(),
    zenodoGetConfig: vi.fn(),
    zenodoTestToken: vi.fn(),
    zenodoSyncDoi: vi.fn(),
    b2shareGetConfig: vi.fn(),
    b2shareTestToken: vi.fn(),
    b2shareSyncPid: vi.fn(),
    gbifGetConfig: vi.fn(),
    gbifTestCredentials: vi.fn(),
    gbifValidateArchive: vi.fn(),
    gbifSyncDoi: vi.fn(),
    gbifInstallations: vi.fn(),
    gbifOrganizationDatasets: vi.fn(),
    s3GetConfig: vi.fn(),
    s3TestConnection: vi.fn(),
    s3UploadStart: vi.fn(),
    s3UploadStatus: vi.fn(),
    publishAllStart: vi.fn(),
    publishAllStatus: vi.fn(),
    listPublishSessions: vi.fn(),
    resumePublishStart: vi.fn(),
    discardPublishSession: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

// Every run now starts the metadata step by asking whether this is a new
// dataset or a new version (see PublicationKindPicker) — the editor below
// it only shows up once answered. Camtrap DP's metadata step also asks
// (right above PublicationKindPicker) whether to upload images to a
// S3-compatible bucket first (see S3ImageUploadPicker) — absent for
// YOLO/software, so answering it here is a no-op there. Most tests don't
// care about it, so default to "No" wherever it's offered.
async function answerNewDataset() {
  const noS3Radio = screen.queryByRole('radio', { name: /^no —/i })
  if (noS3Radio) await userEvent.click(noS3Radio)
  await userEvent.click(await screen.findByRole('radio', { name: /a new dataset/i }))
}

beforeEach(() => {
  vi.clearAllMocks() // call history must not leak between tests (e.g. .not.toHaveBeenCalled() checks)
  mockedApi.trapperGetConfig.mockResolvedValue({ base_url: null, user_name: null, has_password: false })
  // Identity by default (workingDir === the typed path) so existing local-
  // source tests, written before the working-copy split, keep passing
  // unchanged — only a test that cares about the split overrides this.
  mockedApi.resolveLocalSource.mockImplementation(async (path: string) => (
    { status: 'valid' as const, workingDir: path, sourceDir: path, taskId: 'local-session', error: null }
  ))
  mockedApi.yoloResolveLocalSource.mockImplementation(async (path: string) => (
    { status: 'valid' as const, workingDir: `${path}-working`, sourceDir: path, taskId: 'yolo-session', error: null }
  ))
  mockedApi.yoloDataYamlFields.mockResolvedValue({
    title: 'My YOLO', description: null, version: '1.0', homepage: null,
    license: { id: 'MIT', name: 'MIT', url: '' }, authors: [{ name: 'Jane Doe', affiliation: '' }],
    publisher: null, copyright_holders: [],
    class_names: ['cat', 'dog'], split_image_counts: { train: 2, val: 1 }, warnings: [],
  })
  mockedApi.updateYoloDataYaml.mockResolvedValue({ ok: true })
  mockedApi.hfhRepoExists.mockResolvedValue({ exists: false })
  mockedApi.generateProductMetadata.mockResolvedValue({ authors: [] })
  mockedApi.datapackageSummary.mockResolvedValue({ authors: [] })
  // The new metadata-editing step (step === 2) fetches these to pre-fill
  // its form as soon as the source resolves, and patches them back when
  // "Continue" is clicked — default to a no-op shape so tests that don't
  // care about this step's own fields aren't forced to mock it themselves.
  mockedApi.datapackageFields.mockResolvedValue({ name: null, title: null, description: null, version: null, homepage: null })
  mockedApi.updateDatapackageFields.mockResolvedValue({ ok: true })
  // Mirrors settings.toml's own PRODUCT.organizations default (see
  // wildintel_publisher.config.ProductSettings) — WizardPage defaults
  // dpPublisher/dpRightsHolder to organizationOptions[0]/[1] respectively,
  // so this order matters for tests that rely on those defaults.
  mockedApi.organizations.mockResolvedValue([
    { title: 'Institute of Nature Conservation PAS', path: 'https://www.iop.krakow.pl/', email: null },
    { title: 'University of Huelva', path: 'https://www.uhu.es/', email: null },
    { title: 'University of South-Eastern Norway', path: 'https://www.usn.no/', email: null },
    { title: 'German Centre for Integrative Biodiversity Research', path: 'https://www.idiv.de/', email: null },
    { title: 'Spanish National Research Council', path: 'https://www.csic.es/', email: null },
    { title: 'Massachusetts Institute of Technology', path: 'https://www.mit.edu/', email: null },
    { title: 'Spanish Node of the Global Biodiversity Information Facility', path: 'https://www.gbif.es/', email: null },
  ])
  mockedApi.hfhGetConfig.mockResolvedValue({ username: null, output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false })
  mockedApi.zenodoGetConfig.mockResolvedValue({
    environment: 'sandbox', communities: null, output_dir: '/zenodo/output', version: '1.0', timeout: 60, has_token: false,
  })
  mockedApi.b2shareGetConfig.mockResolvedValue({
    environment: 'sandbox', community_id: null, output_dir: '/b2share/output', version: '1.0', timeout: 60, has_token: false,
  })
  mockedApi.gbifGetConfig.mockResolvedValue({
    environment: 'sandbox', publishing_organization_key: null, installation_key: null,
    registry_language: 'eng', output_dir: '/gbif/output', has_credentials: false,
  })
  mockedApi.gbifInstallations.mockResolvedValue([])
})

afterEach(() => {
  vi.useRealTimers()
})

describe('WizardPage', () => {
  it('shows the step indicator with the first step active', () => {
    render(<WizardPage />)

    expect(screen.getByText('Product Type')).toBeInTheDocument()
    expect(screen.getByText('Source')).toBeInTheDocument()
    expect(screen.getByText('Download')).toBeInTheDocument()
  })

  it('shows the six product type options, with Camtrap DP, AI Dataset and Software Application enabled', () => {
    // AI Model/EBV/Image Gallery have no adapter of their own yet (see
    // WizardPage's PRODUCT_OPTIONS comment).
    render(<WizardPage />)

    expect(screen.getByRole('button', { name: /camtrap dp/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /ai dataset/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /software application/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /ai model/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /ebv/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /image gallery/i })).toBeDisabled()
  })

  it('moves straight to the source step when Camtrap DP is clicked', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))

    expect(screen.getByText('Where is it located?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /local directory/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /trapper instance/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /public url/i })).toBeEnabled()
  })

  it('lets the user go back from the source step to the product type step', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /back/i }))

    expect(screen.getByText('What do you want to publish?')).toBeInTheDocument()
  })

  it('lets the user select a source option and highlights it', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))

    const trapperButton = screen.getByRole('button', { name: /trapper instance/i })
    await userEvent.click(trapperButton)

    expect(trapperButton.className).toContain('border-blue-500')
  })
})

async function selectTrapperDeployment(user: ReturnType<typeof userEvent.setup>) {
  mockedApi.trapperTestConnection.mockResolvedValue({ ok: true, research_projects_count: 1 })
  mockedApi.trapperResearchProjects.mockResolvedValue({ results: [{ pk: 1, name: 'Project A', acronym: 'PA' }] })
  mockedApi.trapperClassificationProjects.mockResolvedValue({ results: [{ pk: 10, name: 'Classif A', is_active: true }] })
  mockedApi.trapperDeployments.mockResolvedValue({
    results: [{ pk: 100, deployment_id: 'r0007-dona_0018', location_id: 'L1' }],
  })

  await user.click(screen.getByRole('button', { name: /camtrap dp/i }))
  await user.click(screen.getByRole('button', { name: /trapper instance/i }))
  await user.type(screen.getByPlaceholderText('https://trapper.example.com'), 'https://trapper.example')
  await user.type(screen.getByLabelText('Username'), 'alice')
  await user.type(screen.getByLabelText('Password'), 'secret')
  await user.click(screen.getByRole('button', { name: /test connection/i }))
  await waitFor(() => expect(screen.getByLabelText('Research project')).toBeInTheDocument())
  await user.selectOptions(screen.getByLabelText('Research project'), '1')
  await waitFor(() => expect(screen.getByLabelText('Classification project')).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('Classification project'), '10')
  await waitFor(() => expect(screen.getByLabelText('Deployment')).toBeEnabled())
  await user.selectOptions(screen.getByLabelText('Deployment'), '100')
}

describe('WizardPage download flow', () => {
  it('keeps Next disabled until a deployment is selected', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /trapper instance/i }))

    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()
  })

  it('starts the download and shows the resulting path once a deployment is selected', async () => {
    // Real timers for the connection-form flow (its own internal waitFor
    // polling needs them); fake timers only for WizardPage's own 2s poll
    // delay, so the test doesn't have to actually wait 2 real seconds.
    const user = userEvent.setup()
    render(<WizardPage />)

    await selectTrapperDeployment(user)
    expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled()

    mockedApi.trapperStartDownload.mockResolvedValue({ task_id: 'task-1' })
    mockedApi.trapperDownloadStatus.mockResolvedValue({
      status: 'done', path: '/home/user/Documents/wildintel-publisher/trapper', error: null,
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await answerNewDataset()
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(screen.getByText('Package downloaded')).toBeInTheDocument())
    expect(screen.getByText('/home/user/Documents/wildintel-publisher/trapper')).toBeInTheDocument()
    expect(mockedApi.trapperStartDownload).toHaveBeenCalledWith(
      'https://trapper.example', 'alice', 'secret', 10, 'r0007-dona_0018', true,
    )
  })

  it('shows an error and stays on the source step if the download fails', async () => {
    const user = userEvent.setup()
    render(<WizardPage />)

    await selectTrapperDeployment(user)

    mockedApi.trapperStartDownload.mockResolvedValue({ task_id: 'task-2' })
    mockedApi.trapperDownloadStatus.mockResolvedValue({
      status: 'error', path: null, error: 'Trapper did not return a download URL.',
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByText('Trapper did not return a download URL.')).toBeInTheDocument())
    expect(screen.getByText('Where is it located?')).toBeInTheDocument()
  })
})

describe('WizardPage local directory flow', () => {
  it('keeps Next disabled until the directory is read successfully', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()

    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Camtrap DP', authors: [] })
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')

    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
  })

  it('shows the same result page as the Trapper flow once Next is clicked', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0', authors: [],
    })
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(screen.getByText('Package ready')).toBeInTheDocument()
    expect(screen.getByText('/data/camtrapdp')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open folder/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('A local package.')).toBeInTheDocument())
  })

  it('reuses the same session (never mints a second one) after Back then Next again', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Camtrap DP', authors: [] })
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()
    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /^back$/i }))
    // Re-mounts LocalDirectoryForm with the path it already had — this
    // must reuse the very first call's own session (taskId
    // 'local-session', from the default mock), never mint a fresh one.
    await waitFor(() => expect(mockedApi.resolveLocalSource).toHaveBeenLastCalledWith('/data/camtrapdp', 'local-session'))

    const sessionTaskIdsUsed = mockedApi.resolveLocalSource.mock.calls.map((call) => call[1])
    expect(sessionTaskIdsUsed.filter((id) => id === undefined)).toHaveLength(1) // only the very first call ever mints one
  })

  it('asks the user to complete missing metadata before letting them proceed', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Dataset', authors: [] })
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(screen.getByText('Some details are missing')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()

    mockedApi.completeProductMetadata.mockResolvedValue({
      title: 'My Dataset', description: 'D', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    await userEvent.type(screen.getByLabelText('Description'), 'D')
    await userEvent.type(screen.getByLabelText('Version'), '1.0')
    await userEvent.type(screen.getByLabelText('License ID'), 'CC-BY-4.0')
    await userEvent.type(screen.getByLabelText('License name'), 'CC BY 4.0')
    await userEvent.type(screen.getByLabelText('Author 1 name'), 'Alice')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() => expect(screen.queryByText('Some details are missing')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled()
  })
})

async function reachPublishStep() {
  mockedApi.generateProductMetadata.mockResolvedValue({
    title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
    license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
    authors: [{ name: 'Alice', affiliation: '' }],
  })

  await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
  await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
  await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
  await answerNewDataset()

  await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
}

// Camtrap DP also supports Zenodo/B2SHARE now (see REPOS_BY_PRODUCT_TYPE),
// but several tests below still reach the publish step via a YOLO dataset
// instead, to keep GBIF (Camtrap DP-only, mandatory) out of the way when
// only the generic repo mechanics (config forms, ordering, DOI-primary
// choice) are under test, not anything Camtrap DP-specific.
async function reachPublishStepYolo() {
  mockedApi.generateProductMetadata.mockResolvedValue({
    title: 'My YOLO Dataset', description: 'A local dataset.', version: '1.0',
    license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
    authors: [{ name: 'Alice', affiliation: '' }],
  })

  await userEvent.click(screen.getByRole('button', { name: /ai dataset/i }))
  await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
  await userEvent.type(screen.getByLabelText('Directory'), '/data/yolo')
  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
  await answerNewDataset()

  await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
}

describe('WizardPage coordinate anonymization', () => {
  // These options moved from the source step to the new metadata step (see
  // WizardPage's step === 2) — reachable only once a source has actually
  // resolved, unlike before (when they showed as soon as a source type was
  // picked, on the same step as source selection).
  it('shows the anonymize-coordinates option in the metadata step', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    expect(await screen.findByText('Anonymize deployment coordinates')).toBeInTheDocument()
  })

  it('does not show the anonymize-coordinates option in the metadata step for an AI Dataset', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /ai dataset/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/yolo')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    expect(await screen.findByLabelText('Title')).toHaveValue('My YOLO')
    expect(screen.queryByText('Anonymize deployment coordinates')).not.toBeInTheDocument()
  })

  it('does not show the decimal places field until the checkbox is checked', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()
    await screen.findByText('Anonymize deployment coordinates')

    expect(screen.queryByLabelText(/decimal places/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox', { name: /anonymize deployment coordinates/i }))

    expect(screen.getByLabelText(/decimal places/i)).toBeInTheDocument()
  })

  it('sends the chosen anonymize-coordinates setting to generateProductMetadata when Continue is clicked', async () => {
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()
    await screen.findByText('Anonymize deployment coordinates')

    await userEvent.click(screen.getByRole('checkbox', { name: /anonymize deployment coordinates/i }))
    const decimalsInput = screen.getByLabelText(/decimal places/i)
    await userEvent.clear(decimalsInput)
    await userEvent.type(decimalsInput, '1')

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(mockedApi.generateProductMetadata).toHaveBeenCalledWith(
      '/data/camtrapdp', 'camtrapdp', true, 1, false, 'localhost', 'local-session',
    ))
  })
})

describe('WizardPage YOLO metadata editor', () => {
  async function reachYoloMetadataStep() {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /ai dataset/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/yolo')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()
    await screen.findByLabelText('Title')
  }

  it('works on a session working copy, never on the typed directory', async () => {
    await reachYoloMetadataStep()
    expect(mockedApi.yoloResolveLocalSource).toHaveBeenCalledWith('/data/yolo', undefined)
    expect(mockedApi.yoloDataYamlFields).toHaveBeenCalledWith('/data/yolo-working')
  })

  it('shows the dataset facts and validation warnings', async () => {
    mockedApi.yoloDataYamlFields.mockResolvedValue({
      title: null, description: null, version: null, homepage: null, license: null, authors: [],
      publisher: null, copyright_holders: [],
      class_names: ['cat', 'dog'], split_image_counts: { train: 2, val: 1 },
      warnings: ['3 image(s) under /data/yolo/images have no label file'],
    })
    await reachYoloMetadataStep()
    expect(screen.getByText('cat, dog')).toBeInTheDocument()
    expect(screen.getByText('train: 2 · val: 1')).toBeInTheDocument()
    expect(screen.getByText(/have no label file/)).toBeInTheDocument()
  })

  it('saves the edited metadata into the working copy before generating metadata.json', async () => {
    await reachYoloMetadataStep()
    const title = screen.getByLabelText('Title')
    await userEvent.clear(title)
    await userEvent.type(title, 'Edited title')
    await userEvent.click(screen.getByRole('button', { name: /add author/i }))
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(mockedApi.generateProductMetadata).toHaveBeenCalled())
    expect(mockedApi.updateYoloDataYaml).toHaveBeenCalledWith('/data/yolo-working', {
      title: 'Edited title', description: '', version: '1.0', homepage: '',
      // data.yaml's bare "MIT" completed with its canonical name/URL
      license: { id: 'MIT', name: 'MIT License', url: 'https://opensource.org/licenses/MIT' },
      authors: [{ name: 'Jane Doe', affiliation: '' }],  // the blank added row is dropped
      // data.yaml had neither — defaults to organizations[0]/[1], same as Camtrap DP
      publisher: { name: 'Institute of Nature Conservation PAS', website: 'https://www.iop.krakow.pl/' },
      copyright_holders: ['University of Huelva'],
    })
    expect(mockedApi.updateYoloDataYaml.mock.invocationCallOrder[0])
      .toBeLessThan(mockedApi.generateProductMetadata.mock.invocationCallOrder.at(-1)!)
  })

  it('lets the user pick the publisher and rights holder from the configured organizations', async () => {
    await reachYoloMetadataStep()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Publisher' }), 'Spanish National Research Council')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Rights holder' }), 'Massachusetts Institute of Technology')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(mockedApi.updateYoloDataYaml).toHaveBeenCalled())
    const saved = mockedApi.updateYoloDataYaml.mock.calls[0][1]
    expect(saved.publisher).toEqual({ name: 'Spanish National Research Council', website: 'https://www.csic.es/' })
    expect(saved.copyright_holders).toEqual(['Massachusetts Institute of Technology'])
  })

  it('keeps a publisher from data.yaml that is a configured organization, and warns about one that is not', async () => {
    mockedApi.yoloDataYamlFields.mockResolvedValue({
      title: 'My YOLO', description: null, version: '1.0', homepage: null, license: null, authors: [],
      publisher: { name: 'University of South-Eastern Norway' }, copyright_holders: ['Some Unknown Lab'],
      class_names: ['cat'], split_image_counts: { train: 1, val: 1 }, warnings: [],
    })
    await reachYoloMetadataStep()

    expect(screen.getByRole('combobox', { name: 'Publisher' })).toHaveValue('University of South-Eastern Norway')
    expect(screen.getByRole('combobox', { name: 'Rights holder' })).toHaveValue('University of Huelva')
    expect(screen.getByText(/"Some Unknown Lab" is the rights holder in data.yaml/)).toBeInTheDocument()
  })

  it('defaults the license to CC-BY-NC-4.0 when data.yaml has none', async () => {
    mockedApi.yoloDataYamlFields.mockResolvedValue({
      title: 'My YOLO', description: null, version: '1.0', homepage: null, license: null, authors: [],
      publisher: null, copyright_holders: [],
      class_names: ['cat'], split_image_counts: { train: 1, val: 1 }, warnings: [],
    })
    await reachYoloMetadataStep()

    expect(screen.getByLabelText('License')).toHaveValue('CC-BY-NC-4.0')
    expect(screen.getByText('https://creativecommons.org/licenses/by-nc/4.0/')).toBeInTheDocument()
    expect(screen.queryByLabelText('License ID')).not.toBeInTheDocument()
  })

  it('fills in the whole license from the dropdown, and shows free-text fields for Other', async () => {
    await reachYoloMetadataStep()
    await userEvent.selectOptions(screen.getByLabelText('License'), 'CC0-1.0')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
    await waitFor(() => expect(mockedApi.updateYoloDataYaml).toHaveBeenCalled())
    expect(mockedApi.updateYoloDataYaml.mock.calls[0][1].license).toEqual({
      id: 'CC0-1.0', name: 'Creative Commons Zero v1.0 Universal', url: 'https://creativecommons.org/publicdomain/zero/1.0/',
    })
  })

  it('requires an id or name for a license typed in by hand', async () => {
    await reachYoloMetadataStep()
    await userEvent.selectOptions(screen.getByLabelText('License'), 'Other…')

    expect(screen.getByLabelText('License ID')).toHaveValue('')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('License name'), 'My Own Terms')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('keeps an unrecognized license from data.yaml under Other', async () => {
    mockedApi.yoloDataYamlFields.mockResolvedValue({
      title: 'My YOLO', description: null, version: '1.0', homepage: null,
      license: { id: 'LicenseRef-Custom', name: 'Custom', url: '' }, authors: [],
      publisher: null, copyright_holders: [],
      class_names: ['cat'], split_image_counts: { train: 1, val: 1 }, warnings: [],
    })
    await reachYoloMetadataStep()

    expect(screen.getByLabelText('License')).toHaveValue('__other__')
    expect(screen.getByLabelText('License ID')).toHaveValue('LicenseRef-Custom')
  })

  it('disables Continue while an author has an affiliation but no name', async () => {
    await reachYoloMetadataStep()
    await userEvent.click(screen.getByRole('button', { name: /add author/i }))
    await userEvent.type(screen.getByLabelText('Author 2 affiliation'), 'Somewhere')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()
    expect(screen.getByText('Every author needs a name.')).toBeInTheDocument()
  })
})

const PREVIOUS_V3 = {
  title: 'My YOLO', version: '3.0', warnings: [],
  hfh: { repo_id: 'alice/my-yolo', url: 'https://huggingface.co/datasets/alice/my-yolo', version: '3.0' },
  zenodo: { record_id: '609082', environment: 'sandbox' as const, url: 'https://sandbox.zenodo.org/records/609082', doi: '10.5072/zenodo.609082', version: '3.0' },
  b2share: null, gbif: null,
}

describe('WizardPage new dataset vs. new version', () => {
  async function reachMetadataStepYolo() {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /ai dataset/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/yolo')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
  }

  async function findPreviousVersion() {
    await userEvent.click(await screen.findByRole('radio', { name: /a new version of an already published dataset/i }))
    await userEvent.type(screen.getByLabelText('Previous version identifier'), 'alice/my-yolo')
    await userEvent.click(screen.getByRole('button', { name: /^find$/i }))
  }

  it('asks the question before showing the editor', async () => {
    await reachMetadataStepYolo()

    expect(await screen.findByText('1. What are you publishing?')).toBeInTheDocument()
    expect(screen.queryByText('2. Review metadata')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await answerNewDataset()
    expect(await screen.findByLabelText('Title')).toBeInTheDocument()
    expect(screen.getByText('2. Review metadata')).toBeInTheDocument()
  })

  it('finds the previous version from one identifier, and suggests the next version number', async () => {
    mockedApi.previousVersion.mockResolvedValue(PREVIOUS_V3)
    await reachMetadataStepYolo()
    await findPreviousVersion()

    expect(mockedApi.previousVersion).toHaveBeenCalledWith('hfh', 'alice/my-yolo')
    expect(await screen.findByText('609082')).toBeInTheDocument()
    expect(screen.getByText(/last published version:/i)).toBeInTheDocument()
    // data.yaml said 1.0 — older than the last published 3.0, so bumped
    expect(await screen.findByLabelText('Version')).toHaveValue('4.0')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('lists what was already published to the chosen repository, and looks up the one picked', async () => {
    mockedApi.previousVersion.mockResolvedValue(PREVIOUS_V3)
    mockedApi.zenodoDepositions.mockResolvedValue([
      { id: '609036', title: 'My YOLO' }, { id: '700001', title: 'Something else' },
    ])
    await reachMetadataStepYolo()
    await userEvent.click(await screen.findByRole('radio', { name: /a new version of an already published dataset/i }))
    await userEvent.selectOptions(screen.getByLabelText('Previous version repository'), 'zenodo')
    await waitFor(() => expect(screen.getByLabelText('Previous version environment')).toHaveValue('sandbox'))

    await userEvent.click(screen.getByRole('button', { name: /list what i published here/i }))
    // every listed item also links to its own page, in a new tab
    expect(await screen.findByRole('link', { name: /open something else in a new tab/i }))
      .toHaveAttribute('href', 'https://sandbox.zenodo.org/records/700001')
    await userEvent.click(await screen.findByText('My YOLO'))

    expect(mockedApi.zenodoDepositions).toHaveBeenCalledWith('sandbox', '')
    expect(mockedApi.previousVersion).toHaveBeenCalledWith('zenodo', 'https://sandbox.zenodo.org/records/609036')
    expect(await screen.findByText('609082')).toBeInTheDocument()
  })

  it('filters the published list as the user types', async () => {
    mockedApi.hfhDatasets.mockResolvedValue([
      { id: 'alice/my-yolo', title: 'My YOLO', version: '3.0' },
      { id: 'alice/camtrap', title: 'Camera traps', version: '1.0' },
      { id: 'wildintel/other', title: 'Other thing', version: null },
    ])
    await reachMetadataStepYolo()
    await userEvent.click(await screen.findByRole('radio', { name: /a new version of an already published dataset/i }))
    await userEvent.click(screen.getByRole('button', { name: /list what i published here/i }))
    expect(await screen.findByText('3 found')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Filter published datasets'), 'cam')
    expect(screen.getByText('Camera traps')).toBeInTheDocument()
    expect(screen.queryByText('My YOLO')).not.toBeInTheDocument()
    expect(screen.getByText('1 of 3')).toBeInTheDocument()

    await userEvent.clear(screen.getByLabelText('Filter published datasets'))
    await userEvent.type(screen.getByLabelText('Filter published datasets'), 'zzz')
    expect(screen.getByText(/nothing matches/i)).toBeInTheDocument()
  })

  it('sorts the published list newest first by default, or by title', async () => {
    mockedApi.hfhDatasets.mockResolvedValue([
      { id: 'alice/b', title: 'Bravo', version: '1.0', published: '2026-01-10' },
      { id: 'alice/a', title: 'alpha', version: '1.0', published: '2026-09-25' },
      { id: 'alice/c', title: 'Charlie', version: '1.0', published: null },
    ])
    await reachMetadataStepYolo()
    await userEvent.click(await screen.findByRole('radio', { name: /a new version of an already published dataset/i }))
    await userEvent.click(screen.getByRole('button', { name: /list what i published here/i }))
    await screen.findByText('3 found')

    const titles = () => screen.getAllByRole('link', { name: /^open .* in a new tab$/i })
      .map((a) => a.getAttribute('aria-label')!.replace(/^Open | in a new tab$/g, ''))
    expect(titles()).toEqual(['alpha', 'Bravo', 'Charlie'])  // newest first, undated last
    expect(screen.getByText(/published 2026-09-25/)).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Sort published datasets'), 'title')
    expect(titles()).toEqual(['alpha', 'Bravo', 'Charlie'])

    mockedApi.hfhDatasets.mockResolvedValue([
      { id: 'alice/z', title: 'Zulu', version: '1.0', published: '2026-09-25' },
      { id: 'alice/a', title: 'Alpha', version: '1.0', published: '2026-01-01' },
    ])
    await userEvent.selectOptions(screen.getByLabelText('Sort published datasets'), 'published')
    await userEvent.click(screen.getByRole('button', { name: /list what i published here/i }))
    await screen.findByText('2 found')
    expect(titles()).toEqual(['Zulu', 'Alpha'])
    await userEvent.selectOptions(screen.getByLabelText('Sort published datasets'), 'title')
    expect(titles()).toEqual(['Alpha', 'Zulu'])
  })

  it('lists the Hugging Face Hub datasets of the saved token', async () => {
    mockedApi.previousVersion.mockResolvedValue(PREVIOUS_V3)
    mockedApi.hfhDatasets.mockResolvedValue([{ id: 'alice/my-yolo', title: 'My YOLO', version: '3.0' }])
    await reachMetadataStepYolo()
    await userEvent.click(await screen.findByRole('radio', { name: /a new version of an already published dataset/i }))

    expect(screen.queryByLabelText('Previous version environment')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /list what i published here/i }))
    // Same two-line shape as every other repository: title, then id · version
    const item = await screen.findByRole('button', { name: /my yolo.*alice\/my-yolo.*version.*3\.0/i })
    expect(screen.getByRole('link', { name: /open my yolo in a new tab/i }))
      .toHaveAttribute('href', 'https://huggingface.co/datasets/alice/my-yolo')
    await userEvent.click(item)

    expect(mockedApi.previousVersion).toHaveBeenCalledWith('hfh', 'alice/my-yolo')
  })

  it('blocks a version that is not newer than the last published one', async () => {
    mockedApi.previousVersion.mockResolvedValue(PREVIOUS_V3)
    await reachMetadataStepYolo()
    await findPreviousVersion()
    const version = await screen.findByLabelText('Version')
    await userEvent.clear(version)
    await userEvent.type(version, '3.0')

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()
    expect(screen.getByText(/the last published version is 3\.0/i)).toBeInTheDocument()
  })

  it('shows the lookup error and keeps the editor hidden', async () => {
    mockedApi.previousVersion.mockRejectedValue(new Error("Could not read 'alice/my-yolo': not found"))
    await reachMetadataStepYolo()
    await findPreviousVersion()

    expect(await screen.findByText(/could not read 'alice\/my-yolo'/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()
  })
})

describe('WizardPage contributors editor', () => {
  it('always shows the fixed publisher and rights holder rows, even with no other contributors', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    await screen.findByText('Contributors')
    // Both default to organizationOptions[0]/[1] respectively (see the
    // mocked organizations list in beforeEach) — nothing else to
    // identify a specific contributor by, so no generic per-contributor
    // row is shown.
    expect(screen.getByLabelText('Publisher')).toHaveValue('Institute of Nature Conservation PAS')
    expect(screen.getByLabelText('Rights holder')).toHaveValue('University of Huelva')
    expect(screen.queryByText('Unnamed contributor')).not.toBeInTheDocument()
  })

  it('never sends a null "email" for an organization that has none configured (Camtrap DP schema rejects it)', async () => {
    // Regression test: organizationContributor used to always include an
    // "email" key, defaulting to `null` for any organization without one
    // configured — which is every default entry now that WildINTEL isn't
    // one of them. frictionless then rejected the whole package with
    // "None is not of type 'string' at property 'contributors/0/email'".
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()
    await screen.findByText('Contributors')

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    const call = mockedApi.updateDatapackageFields.mock.calls[0]
    const publisherContributor = call[1].contributors?.[0]
    expect(publisherContributor).not.toHaveProperty('email')
  })

  it('lets the user pick a different publisher, from the same configured organization list as rights holder', async () => {
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()
    await screen.findByText('Contributors')

    // Both dropdowns draw from the exact same configured list.
    const publisherOptionTitles = Array.from(screen.getByLabelText('Publisher').querySelectorAll('option')).map((o) => o.textContent)
    const rightsHolderOptionTitles = Array.from(screen.getByLabelText('Rights holder').querySelectorAll('option')).map((o) => o.textContent)
    expect(publisherOptionTitles).toEqual(rightsHolderOptionTitles)
    expect(publisherOptionTitles).toContain('University of Huelva')

    await userEvent.selectOptions(screen.getByLabelText('Publisher'), 'University of Huelva')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(mockedApi.updateDatapackageFields).toHaveBeenCalledWith('/data/camtrapdp', expect.objectContaining({
      // No "email" key at all — Camtrap DP's own schema rejects `null`
      // there, and this organization has none configured (see
      // organizationContributor's own docstring).
      contributors: expect.arrayContaining([
        { title: 'University of Huelva', path: 'https://www.uhu.es/', role: 'publisher' },
      ]),
    })))
  })

  it('lets the user change only a contributor\'s role, and sends the full array back untouched otherwise', async () => {
    mockedApi.datapackageFields.mockResolvedValue({
      name: null, title: null, description: null, version: null, homepage: null,
      contributors: [
        { title: 'Alice', email: 'alice@example.org', organization: 'Test Org', role: 'principalInvestigator' },
        { title: 'Bob', role: 'contributor' },
      ],
    })
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    await screen.findByText('Alice')
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('alice@example.org · Test Org')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Role for Alice'), 'contact')

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(mockedApi.updateDatapackageFields).toHaveBeenCalledWith('/data/camtrapdp', expect.objectContaining({
      contributors: [
        { title: 'Institute of Nature Conservation PAS', path: 'https://www.iop.krakow.pl/', role: 'publisher' },
        { title: 'University of Huelva', path: 'https://www.uhu.es/', role: 'rightsHolder' },
        { title: 'Alice', email: 'alice@example.org', organization: 'Test Org', role: 'contact' },
        { title: 'Bob', role: 'contributor' },
      ],
    })))
  })

  it('demotes any other publisher/rightsHolder from the source, and pre-selects a matching known rights holder', async () => {
    mockedApi.datapackageFields.mockResolvedValue({
      name: null, title: null, description: null, version: null, homepage: null,
      contributors: [
        { title: 'Someone Else', role: 'publisher' },
        { title: 'University of Huelva', role: 'rightsHolder' },
        { title: 'Alice', role: 'principalInvestigator' },
      ],
    })
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    await screen.findByText('Alice')
    // "Someone Else" (the source's own "publisher") is gone from the
    // generic list — publisher is always one of organizationOptions.
    expect(screen.queryByText('Someone Else')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Rights holder')).toHaveValue('University of Huelva')
    // Warned about the publisher swap (a real change) but not about rights
    // holder (it already matched a known institution — nothing to warn).
    expect(screen.getByText(/"Someone Else" was listed as publisher/)).toBeInTheDocument()
    expect(screen.queryByText(/was listed as rights holder/)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(mockedApi.updateDatapackageFields).toHaveBeenCalledWith('/data/camtrapdp', expect.objectContaining({
      contributors: [
        { title: 'Institute of Nature Conservation PAS', path: 'https://www.iop.krakow.pl/', role: 'publisher' },
        { title: 'University of Huelva', path: 'https://www.uhu.es/', role: 'rightsHolder' },
        { title: 'Alice', role: 'principalInvestigator' },
      ],
    })))
  })

  it('warns when the source\'s rights holder is not one of the selectable institutions', async () => {
    mockedApi.datapackageFields.mockResolvedValue({
      name: null, title: null, description: null, version: null, homepage: null,
      contributors: [{ title: 'Some Other University', role: 'rightsHolder' }],
    })
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await answerNewDataset()

    await screen.findByText(/was listed as rights holder/)
    expect(screen.getByText(/"Some Other University" was listed as rights holder/)).toBeInTheDocument()
    // Falls back to organizationOptions[1] (the rightsHolder default —
    // see WizardPage's own docstring for the [0]=publisher/[1]=rightsHolder
    // convention), since nothing matched.
    expect(screen.getByLabelText('Rights holder')).toHaveValue('University of Huelva')
  })
})

describe('WizardPage Camtrap DP archive flow', () => {
  it('fetches the archive and shows the resulting path', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /public url/i }))
    await userEvent.type(
      screen.getByLabelText(/camtrap dp archive url/i),
      'https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip',
    )
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

    mockedApi.camtrapdpFetchArchiveStart.mockResolvedValue({ task_id: 'fetch-task-1' })
    mockedApi.camtrapdpFetchArchiveStatus.mockResolvedValue({
      status: 'done', path: '/home/user/Documents/wildintel-publisher/camtrapdp-archive/camtrapdp-remote', error: null,
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await answerNewDataset()
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(screen.getByText('Package downloaded')).toBeInTheDocument())
    expect(screen.getByText('/home/user/Documents/wildintel-publisher/camtrapdp-archive/camtrapdp-remote')).toBeInTheDocument()
    expect(mockedApi.camtrapdpFetchArchiveStart).toHaveBeenCalledWith(
      'https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip',
    )
  })

  it('shows an error and stays on the source step if the fetch fails', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /public url/i }))
    await userEvent.type(screen.getByLabelText(/camtrap dp archive url/i), 'https://example.org/datapackage.json')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

    mockedApi.camtrapdpFetchArchiveStart.mockResolvedValue({ task_id: 'fetch-task-2' })
    mockedApi.camtrapdpFetchArchiveStatus.mockResolvedValue({
      status: 'error', path: null, error: 'https://example.org/datapackage.json is not a valid zip archive.',
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    expect(await screen.findByText(/is not a valid zip archive/i)).toBeInTheDocument()
    expect(screen.getByText('Where is it located?')).toBeInTheDocument()
  })

  it('reuses the fetched archive URL as GBIF\'s own, without the standalone-copy note, when GBIF publishes alone', async () => {
    const fetchedUrl = 'https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip'
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A remote package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    mockedApi.camtrapdpFetchArchiveStart.mockResolvedValue({ task_id: 'fetch-task-3' })
    mockedApi.camtrapdpFetchArchiveStatus.mockResolvedValue({
      status: 'done', path: '/home/user/Documents/wildintel-publisher/camtrapdp-archive/camtrapdp-remote', error: null,
    })

    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /public url/i }))
    await userEvent.type(screen.getByLabelText(/camtrap dp archive url/i), fetchedUrl)
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await answerNewDataset()
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))

    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await screen.findByRole('heading', { name: /configure gbif/i })
    await act(async () => {})
    expect(screen.getByLabelText('Archive URL')).toHaveValue(fetchedUrl)
    expect(screen.getByLabelText('Archive URL')).not.toHaveAttribute('readonly')
    expect(screen.queryByText(/the local copy you just fetched/i)).not.toBeInTheDocument()
  })
})

async function reachPublishStepSoftware() {
  mockedApi.generateProductMetadata.mockResolvedValue({
    title: 'My Software', description: 'A software application.', version: '1.0',
    license: { id: 'MIT', name: 'MIT', url: '' },
    authors: [{ name: 'Alice', affiliation: '' }],
  })
  mockedApi.softwareCloneStart.mockResolvedValue({ task_id: 'clone-task-1' })
  mockedApi.softwareCloneStatus.mockResolvedValue({
    status: 'done', path: '/home/user/Documents/wildintel-publisher/software/repo', error: null,
  })

  await userEvent.click(screen.getByRole('button', { name: /software application/i }))
  await userEvent.click(screen.getByRole('button', { name: /git repository/i }))
  await userEvent.type(screen.getByLabelText(/git repository url/i), 'https://github.com/user/repo.git')
  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

  vi.useFakeTimers()
  fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
  await vi.advanceTimersByTimeAsync(2000)
  vi.useRealTimers()

  await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
  await answerNewDataset()
  await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
}

describe('WizardPage metadata errors', () => {
  it('shows the error and stays on the metadata step when generateProductMetadata fails (e.g. a git clone with no CITATION.cff)', async () => {
    mockedApi.generateProductMetadata.mockRejectedValue(
      new Error('/repo has no CITATION.cff — a software application product must provide one at its repository root.'),
    )
    mockedApi.softwareCloneStart.mockResolvedValue({ task_id: 'clone-task-1' })
    mockedApi.softwareCloneStatus.mockResolvedValue({
      status: 'done', path: '/home/user/Documents/wildintel-publisher/software/repo', error: null,
    })
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /software application/i }))
    await userEvent.click(screen.getByRole('button', { name: /git repository/i }))
    await userEvent.type(screen.getByLabelText(/git repository url/i), 'https://github.com/user/repo.git')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await answerNewDataset()
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(await screen.findByText(/has no CITATION\.cff/i)).toBeInTheDocument()
    // Still on the metadata step — never advanced to the download-result step.
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument()
  })

  async function reachConfirmPackageSoftware() {
    mockedApi.softwareCloneStart.mockResolvedValue({ task_id: 'clone-task-1' })
    mockedApi.softwareCloneStatus.mockResolvedValue({
      status: 'done', path: '/home/user/Documents/wildintel-publisher/software/repo', error: null,
    })
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /software application/i }))
    await userEvent.click(screen.getByRole('button', { name: /git repository/i }))
    await userEvent.type(screen.getByLabelText(/git repository url/i), 'https://github.com/user/repo.git')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument())
    await answerNewDataset()
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
  }

  it('confirms the checked-out tag when it matches CITATION.cff\'s version', async () => {
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Software', description: 'A software application.', version: '1.2.0',
      license: { id: 'MIT', name: 'MIT', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
      checked_out_tag: 'v1.2.0',
    })
    await reachConfirmPackageSoftware()

    expect(await screen.findByText(/checked out tag/i)).toBeInTheDocument()
    expect(screen.getByText('v1.2.0')).toBeInTheDocument()
    expect(screen.queryByText(/no git tag matches/i)).not.toBeInTheDocument()
  })

  it('warns when no git tag matches CITATION.cff\'s version', async () => {
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Software', description: 'A software application.', version: '9.9.9',
      license: { id: 'MIT', name: 'MIT', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
      checked_out_tag: null,
    })
    await reachConfirmPackageSoftware()

    expect(await screen.findByText(/no git tag matches/i)).toBeInTheDocument()
    expect(screen.getAllByText('9.9.9')).toHaveLength(2) // shown both in "Version" and the warning itself
    expect(screen.queryByText(/^checked out tag/i)).not.toBeInTheDocument()
  })
})

describe('WizardPage publish step', () => {
  it('advances from the download result to the publish step', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    expect(screen.getByText('Where do you want to publish it?')).toBeInTheDocument()
  })

  it('shows all four repositories enabled for Camtrap DP, with GBIF pre-selected as required', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    // GBIF is always registered for Camtrap DP — pre-selected and not
    // deselectable, same mandatory-repo mechanism Software Application's
    // own Zenodo uses (see MANDATORY_REPOS_BY_PRODUCT_TYPE). Hugging Face
    // Hub, Zenodo, and B2SHARE are all optional alongside it (see
    // REPOS_BY_PRODUCT_TYPE).
    expect(screen.getByRole('button', { name: /hugging face hub/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /gbif/i })).toBeDisabled()
    expect(screen.getByText('Required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /zenodo/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /b2share/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })

  it('does not let the user deselect GBIF for a Camtrap DP', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))

    // Still there — toggling a mandatory repo is a no-op.
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })

  it('shows Zenodo and B2SHARE available for a Software Application, with Zenodo pre-selected as required', async () => {
    render(<WizardPage />)
    await reachPublishStepSoftware()

    // Zenodo's DOI is always what ends up citing the software — it's
    // mandatory, pre-selected, and (unlike every other repo button) its
    // own button stays disabled on purpose: there's nothing to toggle.
    expect(screen.getByRole('button', { name: /zenodo/i })).toBeDisabled()
    expect(screen.getByText('Required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /b2share/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /hugging face hub/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /gbif/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })

  it('does not let the user deselect Zenodo for a Software Application', async () => {
    render(<WizardPage />)
    await reachPublishStepSoftware()

    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))

    // Still there — toggling a mandatory repo is a no-op.
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })

  it('does not show any publish form while still choosing repositories', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))

    expect(screen.queryByLabelText('Version')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })

  it('shows the Hugging Face Hub configuration form first when publishing a Camtrap DP (GBIF tags along, being mandatory)', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    // metadata.json already has a version (the wizard required it to be
    // filled in before Step 3) — this just flushes the sub-form's own
    // settings.toml config-load effect before interacting with it further.
    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure hugging face hub/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument()
    // GBIF is mandatory for Camtrap DP, so it's always the second step too.
    expect(screen.getByText('Step 1 of 2.', { exact: false })).toBeInTheDocument()
  })

  it('shows the Zenodo configuration form after starting publishing a Software Application (Zenodo alone, the mandatory default)', async () => {
    render(<WizardPage />)
    await reachPublishStepSoftware()

    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    // metadata.json already has a version (the wizard required it to be
    // filled in before Step 3) — this just flushes the sub-form's own
    // settings.toml config-load effect before interacting with it further.
    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure zenodo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument()
    expect(screen.getByText('Step 1 of 1.', { exact: false })).toBeInTheDocument()
  })

  it('shows the B2SHARE configuration form after Zenodo, when publishing a Software Application with both selected', async () => {
    render(<WizardPage />)
    await reachPublishStepSoftware()

    await userEvent.click(screen.getByRole('button', { name: /b2share/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure zenodo/i })).toBeInTheDocument()
    expect(screen.getByText('Step 1 of 2.', { exact: false })).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure b2share/i })).toBeInTheDocument()
    expect(screen.getByText('Step 2 of 2.', { exact: false })).toBeInTheDocument()
  })

  it('shows the GBIF configuration form after starting publishing with only GBIF selected', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure gbif/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument()
  })

  it('lets the user deselect an optional repository, keeping Start publishing while the mandatory one remains', async () => {
    // Every implemented product type has a mandatory repo now (GBIF for
    // Camtrap DP, Zenodo for YOLO/Software), so selection can never really
    // reach zero — deselecting an optional repo alongside it is the
    // meaningful case left to test.
    render(<WizardPage />)
    await reachPublishStepYolo()

    const b2shareButton = screen.getByRole('button', { name: /b2share/i })
    await userEvent.click(b2shareButton)
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()

    await userEvent.click(b2shareButton)
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })
})

async function configureHfhAndContinue() {
  await act(async () => {})
  await userEvent.type(screen.getByLabelText('User or organization'), 'alice')
  await userEvent.clear(screen.getByLabelText('Repository name'))
  await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
  await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
  await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
}

// Fills in everything GBIF needs beyond the archive URL (already prefilled
// from an earlier Hugging Face Hub step in the same order — see WizardPage's
// suggestedArchiveUrl) — used as the "second repo" in multi-repo mechanics
// tests (ordering, back-navigation, retry...).
async function configureGbifAndContinue() {
  await act(async () => {})
  await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')
  await userEvent.type(screen.getByLabelText('Installation UUID'), 'inst-1')
  await userEvent.type(screen.getByLabelText('GBIF username'), 'alice')
  await userEvent.type(screen.getByLabelText('GBIF password'), 's3cret')
  await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
}

// Zenodo is mandatory for both YOLO and Software Application — used as the
// "only selected repository" case in single-repo mechanics tests, since
// neither product type can reach a genuinely empty selection anymore.
async function configureZenodoAndContinue() {
  await act(async () => {})
  await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
  await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
}

async function runZenodoPublishToDone() {
  mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
  mockedApi.publishAllStatus.mockResolvedValue({
    status: 'done', error: null, dry_run: false,
    repos: {
      zenodo: {
        status: 'done', stage: 'done', error: null,
        repo_url: 'https://sandbox.zenodo.org/records/1', doi: '10.5281/zenodo.1', pid: null, output_dir: '/zenodo/output',
      },
    },
  })
  vi.useFakeTimers()
  fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
  await vi.advanceTimersByTimeAsync(2000)
  vi.useRealTimers()
}

describe('WizardPage publish order', () => {
  it('does not show a publish-order list with only one repository selected', async () => {
    // Every implemented product type now has a mandatory repo (GBIF for
    // Camtrap DP, Zenodo for YOLO/Software) — Software Application is the
    // one that reaches a genuine single-repo state with no extra clicks,
    // since it has no Hugging Face Hub to add alongside Zenodo.
    render(<WizardPage />)
    await reachPublishStepSoftware()

    expect(screen.queryByText('Publish order')).not.toBeInTheDocument()
  })

  it('always puts Hugging Face Hub first when both HFH and GBIF are selected, with no reordering', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    // Selected in the opposite order — HFH still ends up first, since
    // there's no other valid order once GBIF's archive URL depends on it
    // (see WizardPage's toggleRepo).
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))

    expect(await screen.findByText('Publish order')).toBeInTheDocument()
    expect(screen.getByText(/Hugging Face Hub always publishes first/i)).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /move .* up/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /move .* down/i })).not.toBeInTheDocument()
  })

  it('collects configuration for each repository one screen at a time, then confirms before publishing', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    // Step 1 of 2: configure Hugging Face Hub — nothing published yet.
    await act(async () => {})
    expect(screen.getByText('Step 1 of 2.', { exact: false })).toBeInTheDocument()
    await configureHfhAndContinue()
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()

    // Step 2 of 2: configure GBIF — still nothing published.
    expect(await screen.findByText('Step 2 of 2.', { exact: false })).toBeInTheDocument()
    await configureGbifAndContinue()
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()

    // Both configured — confirmation screen, still nothing published.
    expect(await screen.findByText('Ready to publish')).toBeInTheDocument()
    expect(screen.getByText(/Hugging Face Hub, GBIF/)).toBeInTheDocument()
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()
  })

  it('lets the user go back from "Ready to publish" to reconfigure the last repo, pre-filled', async () => {
    // Regression test: once every repo is configured, "Ready to publish"
    // used to be a dead end — the page-level Back button stays hidden for
    // the whole step 4 && publishStarted stretch on purpose (see its own
    // condition), and this screen had no button of its own to get back
    // into the per-repo configuration forms.
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureHfhAndContinue()
    await configureGbifAndContinue()
    await screen.findByText('Ready to publish')

    await userEvent.click(screen.getByRole('button', { name: /back to gbif/i }))

    expect(await screen.findByText('Step 2 of 2.', { exact: false })).toBeInTheDocument()
    expect(screen.getByLabelText('Publishing organization UUID')).toHaveValue('org-1')

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(await screen.findByText('Ready to publish')).toBeInTheDocument()
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()
  })

  it('lets the user go back to a previous repository without losing what was typed', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    expect(screen.queryByRole('button', { name: /back to hugging face hub/i })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /back to hugging face hub/i }))

    await screen.findByText('Step 1 of 2.', { exact: false })
    // No "Back" button on the very first configured repository.
    expect(screen.queryByRole('button', { name: /^back to/i })).not.toBeInTheDocument()
    await act(async () => {})
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
    expect(screen.getByLabelText('Repository name')).toHaveValue('dataset')
    expect(screen.getByLabelText('HuggingFace Hub token')).toHaveValue('hf_x')
  })

  it('lets the user jump back to a previous repository by clicking its step in the breadcrumb', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })

    // The already-configured first step shows a checkmark and is clickable,
    // same effect as the current step's own "Back to X" button.
    await userEvent.click(screen.getByRole('button', { name: /✓.*hugging face hub/i }))

    await screen.findByText('Step 1 of 2.', { exact: false })
    await act(async () => {})
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
  })

  it('prefills the GBIF archive URL from an earlier Hugging Face Hub step in the same order', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()

    await screen.findByRole('heading', { name: /configure gbif/i })
    await act(async () => {})
    expect(screen.getByLabelText('Archive URL')).toHaveValue(
      'https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip',
    )
  })

  it('still prefills/locks the GBIF archive URL when Hugging Face Hub is publishing in Link mode', async () => {
    // camtrapdp-remote.zip is now generated by HFH's own upload regardless
    // of Mirror/Link mode (see hfh.upload_to_huggingface) — the zip's own
    // HFH URL is just as deterministic and permanent either way, so the
    // field behaves the same as the Mirror-mode case.
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await act(async () => {})
    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))
    await userEvent.type(screen.getByLabelText('User or organization'), 'alice')
    await userEvent.clear(screen.getByLabelText('Repository name'))
    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await screen.findByRole('heading', { name: /configure gbif/i })
    await act(async () => {})
    expect(screen.getByLabelText('Archive URL')).toHaveValue(
      'https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip',
    )
    expect(screen.getByLabelText('Archive URL')).toHaveAttribute('readonly')
  })

  it('leaves the GBIF archive URL blank and unlocked when Zenodo publishes without Hugging Face Hub', async () => {
    // Unlike Hugging Face Hub's user-chosen repo_id, Zenodo's own deposition
    // id (and so its file's own public URL) is only assigned once it
    // actually uploads — nothing to prefill/lock from it here. GBIF is
    // mandatory and pre-selected the moment Camtrap DP is picked, so it's
    // already Step 1 here — Zenodo (added afterward by clicking it) ends up
    // Step 2, but that ordering doesn't matter for this assertion, since
    // nothing is derived live from Zenodo either way.
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await screen.findByRole('heading', { name: /configure gbif/i })
    await act(async () => {})
    expect(screen.getByLabelText('Archive URL')).toHaveValue('')
    expect(screen.getByLabelText('Archive URL')).not.toHaveAttribute('readonly')
    expect(screen.getByText(/their own record isn't assigned until they actually upload/i)).toBeInTheDocument()
  })

  it('never asks which DOI is primary for an AI Dataset — the backend picks Zenodo', async () => {
    render(<WizardPage />)
    await reachPublishStepYolo()

    // Zenodo is mandatory for YOLO — already selected once
    // reachPublishStepYolo runs, nothing to click for it here.
    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /b2share/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await act(async () => {})
    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await screen.findByText('Step 2 of 3.', { exact: false })
    await configureHfhAndContinue()

    await screen.findByText('Step 3 of 3.', { exact: false })
    await act(async () => {})
    await userEvent.type(screen.getByLabelText('B2SHARE token'), 'b2_x')
    await userEvent.type(screen.getByLabelText('Community UUID'), 'uuid-1')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(await screen.findByText('Ready to publish')).toBeInTheDocument()
    expect(screen.queryByText(/Which DOI should Hugging Face Hub cite as primary\?/)).not.toBeInTheDocument()

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({ status: 'running', error: null, dry_run: false, repos: {} })
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))

    await waitFor(() => expect(mockedApi.publishAllStart).toHaveBeenCalled())
    expect(mockedApi.publishAllStart.mock.calls[0][0].primaryDoiSource).toBeUndefined()
  })

  it('asks which DOI is primary for HFH when a Camtrap DP goes to hfh + zenodo + b2share, then passes the choice along', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    // GBIF is mandatory for Camtrap DP — already selected.
    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /b2share/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    for (let step = 1; step <= 4; step++) {
      await screen.findByText(`Step ${step} of 4.`, { exact: false })
      await act(async () => {})
      if (screen.queryByLabelText('HuggingFace Hub token')) await configureHfhAndContinue()
      else if (screen.queryByLabelText('GBIF username')) await configureGbifAndContinue()
      else if (screen.queryByLabelText('Zenodo token')) {
        await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
        await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
      } else {
        await userEvent.type(screen.getByLabelText('B2SHARE token'), 'b2_x')
        await userEvent.type(screen.getByLabelText('Community UUID'), 'uuid-1')
        await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
      }
    }

    expect(await screen.findByText(/Which DOI should Hugging Face Hub cite as primary\?/)).toBeInTheDocument()
    expect(screen.queryByText('Ready to publish')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /b2share \(eudat\)/i }))
    expect(await screen.findByText('Ready to publish')).toBeInTheDocument()

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({ status: 'running', error: null, dry_run: false, repos: {} })
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))

    await waitFor(() => expect(mockedApi.publishAllStart).toHaveBeenCalledWith(
      expect.objectContaining({ primaryDoiSource: 'b2share' }),
    ))
  })

  it('publishes every repository in one backend call, in the chosen order', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureGbifAndContinue()

    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
        gbif: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://registry.gbif-test.org/dataset/123', doi: null, pid: null, output_dir: '/gbif/output',
        },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    expect(mockedApi.publishAllStart).toHaveBeenCalledWith(expect.objectContaining({
      repos: [
        expect.objectContaining({ repo: 'hfh', repoId: 'alice/dataset' }),
        expect.objectContaining({ repo: 'gbif', publishingOrganizationKey: 'org-1' }),
      ],
    }))
    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
  })

  it('uploads the images from Continue to the chosen S3 remote, showing its progress', async () => {
    mockedApi.s3GetConfig.mockResolvedValue({
      remotes: [{
        id: 'r1', name: 'WildINTEL', endpoint_url: null, region: null, bucket: 'my-bucket', prefix: null,
        public_base_url: null, verify_ssl: true, has_access_key: true, has_secret_key: true,
      }],
    })
    mockedApi.s3TestConnection.mockResolvedValue({ ok: true })
    mockedApi.generateProductMetadata.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })

    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))

    // Continue stays disabled until the S3 question itself is answered,
    // even once the publication kind is chosen — same gate as the missing-
    // metadata/version checks right alongside it.
    await userEvent.click(await screen.findByRole('radio', { name: /a new dataset/i }))
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.click(screen.getByRole('radio', { name: /^yes —/i }))
    await waitFor(() => expect(mockedApi.s3GetConfig).toHaveBeenCalled())
    // The only saved remote is pre-selected.
    await waitFor(() => expect(screen.getByLabelText('Remote')).toHaveValue('r1'))
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))
    await waitFor(() => expect(screen.getByText(/connection successful/i)).toBeInTheDocument())

    mockedApi.s3UploadStart.mockResolvedValue({ task_id: 's3-task' })
    mockedApi.s3UploadStatus
      .mockResolvedValueOnce({
        status: 'running', stage: 'uploading', error: null, downloaded_images: 3, uploaded: 1, total: 3, rewritten: null, dry_run: false, log: [],
      })
      .mockResolvedValue({
        status: 'done', stage: 'done', error: null, downloaded_images: 3, uploaded: 3, total: 3, rewritten: 3, dry_run: false, log: [],
      })

    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(await screen.findByText(/\(1\/3\)/, {}, { timeout: 3000 })).toBeInTheDocument()
    expect(mockedApi.s3UploadStart).toHaveBeenCalledWith(
      '/data/camtrapdp', expect.objectContaining({ remoteId: 'r1' }), expect.anything(),
    )

    // Once the upload is done, the wizard moves on to choosing where to publish.
    expect(await screen.findByRole('button', { name: /^next$/i }, { timeout: 4000 })).toBeInTheDocument()
  })

  it('shows the GBIF Sync DOI section only when this run\'s registration actually returned a DOI', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: null, output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false,
    })
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureGbifAndContinue()
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
        gbif: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://registry.gbif-test.org/dataset/123', doi: '10.21373/eet8jz', pid: null, output_dir: '/gbif/output',
        },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.getByText('Sync DOI to Hugging Face Hub')).toBeInTheDocument()
  })

  it('shows an automatic-sync confirmation instead of the manual form when the backend already synced the DOI', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureGbifAndContinue()
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
        gbif: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://registry.gbif-test.org/dataset/123', doi: '10.21373/eet8jz', pid: null,
          output_dir: '/gbif/output', doi_synced_to_hfh: true,
        },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.queryByText('Sync DOI to Hugging Face Hub')).not.toBeInTheDocument()
    expect(screen.getByText(/automatically synced/i)).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'https://huggingface.co/datasets/alice/dataset' }).length).toBe(2)
  })

  it('does not show the GBIF Sync DOI section when this run\'s registration got no DOI', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureGbifAndContinue()
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
        gbif: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://registry.gbif-test.org/dataset/123', doi: null, pid: null, output_dir: '/gbif/output',
        },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.queryByText('Sync DOI to Hugging Face Hub')).not.toBeInTheDocument()
  })

  it('stops the sequence and shows the error if a repository fails to publish', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureGbifAndContinue()
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'error', error: 'Invalid or unauthorized HuggingFace Hub token.', dry_run: false,
      repos: {
        hfh: {
          status: 'error', stage: 'uploading', error: 'Invalid or unauthorized HuggingFace Hub token.',
          repo_url: null, doi: null, pid: null, output_dir: null,
        },
        gbif: { status: 'pending', stage: '', error: null, repo_url: null, doi: null, pid: null, output_dir: null },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    expect((await screen.findAllByText(/Invalid or unauthorized HuggingFace Hub token\./)).length).toBeGreaterThan(0)
    expect(screen.queryByText('All done!')).not.toBeInTheDocument()
  })

  it('shows the repo URL and retries only the failed repository, keeping the already-done one untouched', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /gbif/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureGbifAndContinue()
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValueOnce({ task_id: 'publish-task-1' })
    mockedApi.publishAllStatus.mockResolvedValueOnce({
      status: 'error', error: 'Missing GBIF publishing organization/installation.', dry_run: false,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
        gbif: {
          status: 'error', stage: 'releasing', error: 'Missing GBIF publishing organization/installation.',
          repo_url: null, doi: null, pid: null, output_dir: null,
        },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    // Hugging Face Hub already succeeded — its "Done" status and repo URL
    // must stay visible even though the overall task ended in error.
    expect(await screen.findByText('https://huggingface.co/datasets/alice/dataset')).toBeInTheDocument()
    expect(screen.getByText('Missing GBIF publishing organization/installation.')).toBeInTheDocument()

    mockedApi.publishAllStart.mockResolvedValueOnce({ task_id: 'publish-task-2' })
    mockedApi.publishAllStatus.mockResolvedValueOnce({
      status: 'done', error: null, dry_run: false,
      repos: {
        gbif: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://registry.gbif-test.org/dataset/123', doi: null, pid: null, output_dir: '/gbif/output',
        },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /retry failed repositories/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    // Only the failed repo is retried — Hugging Face Hub is never
    // re-published, and the retry chains from HFH's own finalized output.
    expect(mockedApi.publishAllStart).toHaveBeenLastCalledWith(expect.objectContaining({
      inputDir: '/hfh/output',
      repos: [expect.objectContaining({ repo: 'gbif' })],
    }))

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.getByText('https://huggingface.co/datasets/alice/dataset')).toBeInTheDocument()
    expect(screen.getByText('https://registry.gbif-test.org/dataset/123')).toBeInTheDocument()
  })

  it('shows an "All done!" screen once the only selected repository finishes publishing', async () => {
    // Every implemented product type now has a mandatory repo (GBIF for
    // Camtrap DP, Zenodo for YOLO/Software) — Software Application is the
    // one that reaches a genuine single-repo publish with no extra clicks,
    // since it has no Hugging Face Hub to add alongside Zenodo.
    render(<WizardPage />)
    await reachPublishStepSoftware()

    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureZenodoAndContinue()
    await screen.findByText('Ready to publish')

    await runZenodoPublishToDone()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.getByText(/Published to: Zenodo\./)).toBeInTheDocument()
  })

  it('offers the manual Zenodo "Sync DOI to Hugging Face Hub" form when HFH is not part of the run', async () => {
    render(<WizardPage />)
    await reachPublishStepSoftware()

    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureZenodoAndContinue()
    await screen.findByText('Ready to publish')
    await runZenodoPublishToDone()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.getByText('Sync DOI to Hugging Face Hub')).toBeInTheDocument()
  })

  it('hides the manual Zenodo sync form when HFH was published in the same run', async () => {
    render(<WizardPage />)
    await reachPublishStepYolo()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureZenodoAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await configureHfhAndContinue()
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        zenodo: { status: 'done', stage: 'done', error: null, repo_url: 'https://sandbox.zenodo.org/records/1', doi: '10.5281/zenodo.1', pid: null, output_dir: '/zenodo/output' },
        hfh: { status: 'done', stage: 'done', error: null, repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output' },
      },
    })
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.queryByText('Sync DOI to Hugging Face Hub')).not.toBeInTheDocument()
  })

  it('resets back to the first step when "Publish again" is clicked', async () => {
    render(<WizardPage />)
    await reachPublishStepSoftware()

    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureZenodoAndContinue()
    await screen.findByText('Ready to publish')

    await runZenodoPublishToDone()
    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: /^publish again$/i }))

    expect(screen.getByText('What do you want to publish?')).toBeInTheDocument()
    expect(screen.queryByText('All done!')).not.toBeInTheDocument()
  })

  it('hides the global Back button once publishing has started', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument()
  })
})

const HFH_ONLY_RESUME_SESSION: PublishSessionSummary = {
  task_id: 'resume-task-1',
  created_at: '2026-09-01T10:00:00Z',
  status: 'error',
  phase: 'publishing',
  product_type: 'camtrapdp',
  source_type: 'trapper',
  dry_run: false,
  input_dir: '/tmp/camtrapdp',
  media_dir: null,
  primary_doi_source: null,
  repos: [
    { repo: 'hfh', output_dir: '/hfh/output', repo_id: 'alice/dataset', private: true, mirror_images: true, output_mode: 'prepared' },
  ],
  repo_status: {
    hfh: {
      status: 'error', stage: 'uploading', error: 'network blip',
      repo_url: null, doi: null, pid: null, output_dir: null,
    },
  },
}

const PREPROCESSED_RESUME_SESSION: PreprocessingSession = {
  task_id: 'resume-task-2',
  created_at: '2026-09-01T10:00:00Z',
  status: 'done',
  phase: 'preprocessed',
  product_type: 'camtrapdp',
  source_type: 'local',
  fetch: {
    source_type: 'local', params: { path: '/data/camtrapdp' },
    output_dir: '/sessions/resume-task-2/source', input_dir: '/sessions/resume-task-2/source/abc123',
  },
  preprocessing: {
    status: 'done', anonymize_coordinates: true, coordinate_decimals: 1, randomize_media_ids: false, media_id_domain: 'localhost',
  },
}

describe('WizardPage resume', () => {
  it('lands on step 3 with a usable Next button, reading metadata.json back instead of re-preprocessing', async () => {
    mockedApi.datapackageSummary.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })

    render(<WizardPage resumeSession={PREPROCESSED_RESUME_SESSION} />)

    await waitFor(() => expect(screen.getByText('My Camtrap DP')).toBeInTheDocument())
    expect(mockedApi.datapackageSummary).toHaveBeenCalledWith('/sessions/resume-task-2/source/abc123')
    expect(mockedApi.generateProductMetadata).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled()
  })

  it('lets a "preprocessed"-phase resume pick repos normally, instead of jumping straight to "ready to confirm"', async () => {
    // Regression test: publishStarted/resumeTaskId used to seed from
    // "any resumeSession at all" (`!!resumeSession`) instead of "one
    // already past repo selection" (phase === 'publishing') — so a
    // "fetched"/"preprocessed" resume (nothing chosen yet) skipped
    // straight to the "all configured, ready to publish" screen with an
    // EMPTY repo list, and clicking through it called resumePublishStart
    // against a session with no "repos" key yet, which the backend
    // rejects with "No interrupted publish session found".
    mockedApi.datapackageSummary.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })

    render(<WizardPage resumeSession={PREPROCESSED_RESUME_SESSION} />)
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))

    expect(screen.getByRole('heading', { name: /where do you want to publish it\?/i })).toBeInTheDocument()
    expect(screen.queryByText(/ready to publish|will now start/i)).not.toBeInTheDocument()
    expect(mockedApi.resumePublishStart).not.toHaveBeenCalled()
  })

  it('pre-selects the mandatory repo on a resumed repo-picker screen, so it can actually be published', async () => {
    // Regression test: a mandatory repo (GBIF, for Camtrap DP) is normally
    // seeded into selectedRepos/publishOrder by step 0's own product-type
    // button — a resumed session skips step 0 entirely, so it showed up
    // marked "Required" and permanently disabled, yet was never actually
    // selected (toggleRepo refuses to change a mandatory repo's own
    // selection either), leaving no way to turn it on and no "Start
    // publishing" button at all (gated on selectedRepos.size > 0).
    mockedApi.datapackageSummary.mockResolvedValue({
      title: 'My Camtrap DP', description: 'A local package.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })

    render(<WizardPage resumeSession={PREPROCESSED_RESUME_SESSION} />)
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: /where do you want to publish it\?/i })).toBeInTheDocument())

    expect(screen.getByRole('button', { name: /gbif/i })).toHaveClass('border-blue-500')
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    expect(await screen.findByText('Configure GBIF')).toBeInTheDocument()
  })

  it('skips straight to configuring the persisted repos, pre-filled minus the token', async () => {
    render(<WizardPage resumeSession={HFH_ONLY_RESUME_SESSION} />)

    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure hugging face hub/i })).toBeInTheDocument()
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
    expect(screen.getByLabelText('Repository name')).toHaveValue('dataset')
    // Never persisted — the user must always retype it.
    expect(screen.getByLabelText('HuggingFace Hub token')).toHaveValue('')
  })

  it('calls resumePublishStart (not publishAllStart) once every repo is reconfigured', async () => {
    mockedApi.resumePublishStart.mockResolvedValue({ task_id: 'resume-task-1' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
      },
    })

    render(<WizardPage resumeSession={HFH_ONLY_RESUME_SESSION} />)
    // User/org and repository name are already pre-filled from the session
    // (see the first test above) — only the token needs retyping.
    await act(async () => {})
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await act(async () => {})
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    expect(mockedApi.resumePublishStart).toHaveBeenCalledWith(
      'resume-task-1',
      expect.arrayContaining([expect.objectContaining({ repo: 'hfh', token: 'hf_x', repoId: 'alice/dataset' })]),
      undefined, 60,
    )
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()
  })
})
