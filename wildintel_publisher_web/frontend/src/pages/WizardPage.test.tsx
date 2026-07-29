import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
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
    generateProductMetadata: vi.fn(),
    completeProductMetadata: vi.fn(),
    datapackageSummary: vi.fn(),
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
    publishAllStart: vi.fn(),
    publishAllStatus: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  vi.clearAllMocks() // call history must not leak between tests (e.g. .not.toHaveBeenCalled() checks)
  mockedApi.trapperGetConfig.mockResolvedValue({ base_url: null, user_name: null, has_password: false })
  mockedApi.generateProductMetadata.mockResolvedValue({ authors: [] })
  mockedApi.datapackageSummary.mockResolvedValue({ authors: [] })
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

  it('shows the six product type options, with Camtrap DP, YOLO Dataset and Software Application enabled', () => {
    // AI Model/EBV/Image Gallery have no adapter of their own yet (see
    // WizardPage's PRODUCT_OPTIONS comment).
    render(<WizardPage />)

    expect(screen.getByRole('button', { name: /camtrap dp/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /yolo dataset/i })).toBeEnabled()
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

    await waitFor(() => expect(screen.getByText('Package downloaded')).toBeInTheDocument())
    expect(screen.getByText('/home/user/Documents/wildintel-publisher/trapper')).toBeInTheDocument()
    expect(mockedApi.trapperStartDownload).toHaveBeenCalledWith(
      'https://trapper.example', 'alice', 'secret', 10, 'r0007-dona_0018',
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

    expect(screen.getByText('Package ready')).toBeInTheDocument()
    expect(screen.getByText('/data/camtrapdp')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open folder/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('A local package.')).toBeInTheDocument())
  })

  it('asks the user to complete missing metadata before letting them proceed', async () => {
    render(<WizardPage />)

    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Dataset', authors: [] })
    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))

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

  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
}

// Camtrap DP is now restricted to HFH+GBIF only (see REPOS_BY_PRODUCT_TYPE)
// — tests that need Zenodo/B2SHARE available reach the publish step via a
// YOLO dataset instead, which still supports all three of HFH/Zenodo/
// B2SHARE. Only the repo mechanics (config forms, ordering, DOI-primary
// choice) are under test in those cases, not anything Camtrap DP-specific.
async function reachPublishStepYolo() {
  mockedApi.generateProductMetadata.mockResolvedValue({
    title: 'My YOLO Dataset', description: 'A local dataset.', version: '1.0',
    license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
    authors: [{ name: 'Alice', affiliation: '' }],
  })

  await userEvent.click(screen.getByRole('button', { name: /yolo dataset/i }))
  await userEvent.click(screen.getByRole('button', { name: /local directory/i }))
  await userEvent.type(screen.getByLabelText('Directory'), '/data/yolo')
  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))

  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
}

describe('WizardPage coordinate anonymization', () => {
  it('shows the anonymize-coordinates option once a Camtrap DP source is picked', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    expect(screen.getByText('Anonymize deployment coordinates')).toBeInTheDocument()
  })

  it('does not show the anonymize-coordinates option for a YOLO Dataset', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /yolo dataset/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    expect(screen.queryByText('Anonymize deployment coordinates')).not.toBeInTheDocument()
  })

  it('does not show the decimal places field until the checkbox is checked', async () => {
    render(<WizardPage />)
    await userEvent.click(screen.getByRole('button', { name: /camtrap dp/i }))
    await userEvent.click(screen.getByRole('button', { name: /local directory/i }))

    expect(screen.queryByLabelText(/decimal places/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox'))

    expect(screen.getByLabelText(/decimal places/i)).toBeInTheDocument()
  })

  it('sends the chosen anonymize-coordinates setting to generateProductMetadata, once, as preprocessing', async () => {
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

    await userEvent.click(screen.getByRole('checkbox'))
    const decimalsInput = screen.getByLabelText(/decimal places/i)
    await userEvent.clear(decimalsInput)
    await userEvent.type(decimalsInput, '1')

    await userEvent.click(screen.getByRole('button', { name: /^next$/i }))

    await waitFor(() => expect(mockedApi.generateProductMetadata).toHaveBeenCalledWith(
      '/data/camtrapdp', 'camtrapdp', true, 1,
    ))
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

  await waitFor(() => expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument())
  await userEvent.click(screen.getByRole('button', { name: /^next$/i }))
}

describe('WizardPage publish step', () => {
  it('advances from the download result to the publish step', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    expect(screen.getByText('Where do you want to publish it?')).toBeInTheDocument()
  })

  it('shows only Hugging Face Hub and GBIF enabled for Camtrap DP, with GBIF pre-selected as required', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    // GBIF is always registered for Camtrap DP — pre-selected and not
    // deselectable, same mandatory-repo mechanism Software Application's
    // own Zenodo uses (see MANDATORY_REPOS_BY_PRODUCT_TYPE).
    expect(screen.getByRole('button', { name: /hugging face hub/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /gbif/i })).toBeDisabled()
    expect(screen.getByText('Required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /zenodo/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /b2share/i })).toBeDisabled()
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
// tests (ordering, back-navigation, retry...) now that Zenodo/B2SHARE are
// temporarily unavailable in the wizard (see REPO_OPTIONS's own comment).
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

  it('does not prefill/lock the GBIF archive URL when Hugging Face Hub is publishing in Link mode', async () => {
    // camtrapdp-remote.zip is only ever generated by HFH's own Mirror mode
    // (see hfh.upload_to_huggingface) — Link mode never creates it, so
    // there's nothing deterministic to point GBIF at; the field must behave
    // exactly like the no-HFH (standalone registration) case instead.
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
    expect(screen.getByLabelText('Archive URL')).toHaveValue('')
    expect(screen.getByLabelText('Archive URL')).not.toHaveAttribute('readonly')
    expect(screen.getByText(/not from Hugging Face Hub either/i)).toBeInTheDocument()
  })

  it('asks which DOI is primary for HFH only when hfh + zenodo + b2share are all selected, then passes the choice along', async () => {
    render(<WizardPage />)
    await reachPublishStepYolo()

    // Zenodo is mandatory for YOLO — already selected (and first in publish
    // order, since it's added the moment the product type is picked) once
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

    expect(await screen.findByText(/Which DOI should Hugging Face Hub cite as primary\?/)).toBeInTheDocument()
    expect(screen.queryByText('Ready to publish')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /b2share \(eudat\)/i }))

    expect(await screen.findByText('Ready to publish')).toBeInTheDocument()

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null, dry_run: false,
      repos: {
        hfh: { status: 'done', stage: 'done', error: null, repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output' },
        zenodo: { status: 'done', stage: 'done', error: null, repo_url: 'https://zenodo.org/records/1', doi: '10.5281/zenodo.1', pid: null, output_dir: '/zenodo/output' },
        b2share: { status: 'done', stage: 'done', error: null, repo_url: 'https://b2share.eudat.eu/records/1', doi: null, pid: '10.1234/b2share.1', output_dir: '/b2share/output' },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    expect(mockedApi.publishAllStart).toHaveBeenCalledWith(expect.objectContaining({ primaryDoiSource: 'b2share' }))
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
