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

  it('shows the five product type options, Camtrap DP and YOLO enabled', () => {
    render(<WizardPage />)

    expect(screen.getByRole('button', { name: /camtrap dp/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /yolo dataset/i })).toBeEnabled()
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

describe('WizardPage publish step', () => {
  it('advances from the download result to the publish step', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    expect(screen.getByText('Where do you want to publish it?')).toBeInTheDocument()
  })

  it('shows Hugging Face Hub, Zenodo and B2SHARE enabled, and GBIF disabled', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    expect(screen.getByRole('button', { name: /hugging face hub/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /zenodo/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /b2share/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /gbif/i })).toBeDisabled()
  })

  it('does not show any publish form while still choosing repositories', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))

    expect(screen.queryByLabelText('Version')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start publishing/i })).toBeInTheDocument()
  })

  it('shows the Hugging Face Hub configuration form after starting publishing with only HFH selected', async () => {
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
    expect(screen.getByText('Step 1 of 1.', { exact: false })).toBeInTheDocument()
  })

  it('shows the Zenodo configuration form after starting publishing with only Zenodo selected', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    // metadata.json already has a version (the wizard required it to be
    // filled in before Step 3) — this just flushes the sub-form's own
    // settings.toml config-load effect before interacting with it further.
    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure zenodo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument()
  })

  it('shows the B2SHARE configuration form after starting publishing with only B2SHARE selected', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /b2share/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    // metadata.json already has a version (the wizard required it to be
    // filled in before Step 3) — this just flushes the sub-form's own
    // settings.toml config-load effect before interacting with it further.
    await act(async () => {})
    expect(screen.getByRole('heading', { name: /configure b2share/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeInTheDocument()
  })

  it('lets the user deselect a repository before starting publishing', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    const hfhButton = screen.getByRole('button', { name: /hugging face hub/i })
    await userEvent.click(hfhButton)
    await userEvent.click(hfhButton)

    expect(screen.queryByRole('button', { name: /start publishing/i })).not.toBeInTheDocument()
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

async function runHfhPublishToDone() {
  mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
  mockedApi.publishAllStatus.mockResolvedValue({
    status: 'done', error: null,
    repos: {
      hfh: {
        status: 'done', stage: 'done', error: null,
        repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
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
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))

    expect(screen.queryByText('Publish order')).not.toBeInTheDocument()
  })

  it('shows a reorderable list, in selection order, once more than one repo is selected', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))

    expect(await screen.findByText('Publish order')).toBeInTheDocument()
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('1.')
    expect(items[0]).toHaveTextContent('Hugging Face Hub')
    expect(items[1]).toHaveTextContent('2.')
    expect(items[1]).toHaveTextContent('Zenodo')
  })

  it('lets the user move a repository up in the publish order', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await screen.findByText('Publish order')

    await userEvent.click(screen.getByRole('button', { name: /move zenodo up/i }))

    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Zenodo')
    expect(items[1]).toHaveTextContent('Hugging Face Hub')
  })

  it('collects configuration for each repository one screen at a time, then confirms before publishing', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    // Step 1 of 2: configure Hugging Face Hub — nothing published yet.
    await act(async () => {})
    expect(screen.getByText('Step 1 of 2.', { exact: false })).toBeInTheDocument()
    await configureHfhAndContinue()
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()

    // Step 2 of 2: configure Zenodo — still nothing published.
    expect(await screen.findByText('Step 2 of 2.', { exact: false })).toBeInTheDocument()
    await act(async () => {})
    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()

    // Both configured — confirmation screen, still nothing published.
    expect(await screen.findByText('Ready to publish')).toBeInTheDocument()
    expect(screen.getByText(/Hugging Face Hub, Zenodo/)).toBeInTheDocument()
    expect(mockedApi.publishAllStart).not.toHaveBeenCalled()
  })

  it('asks which DOI is primary for HFH only when hfh + zenodo + b2share are all selected, then passes the choice along', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /b2share/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 3.', { exact: false })
    await act(async () => {})
    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

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
      status: 'done', error: null,
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
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await act(async () => {})
    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'done', error: null,
      repos: {
        hfh: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output',
        },
        zenodo: {
          status: 'done', stage: 'done', error: null,
          repo_url: 'https://zenodo.org/records/123', doi: '10.5281/zenodo.123', pid: null, output_dir: '/zenodo/output',
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
        expect.objectContaining({ repo: 'zenodo', token: 'zen_x' }),
      ],
    }))
    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
  })

  it('stops the sequence and shows the error if a repository fails to publish', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /zenodo/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))

    await configureHfhAndContinue()
    await screen.findByText('Step 2 of 2.', { exact: false })
    await act(async () => {})
    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))
    await screen.findByText('Ready to publish')

    mockedApi.publishAllStart.mockResolvedValue({ task_id: 'publish-task' })
    mockedApi.publishAllStatus.mockResolvedValue({
      status: 'error', error: 'Invalid or unauthorized HuggingFace Hub token.',
      repos: {
        hfh: {
          status: 'error', stage: 'uploading', error: 'Invalid or unauthorized HuggingFace Hub token.',
          repo_url: null, doi: null, pid: null, output_dir: null,
        },
        zenodo: { status: 'pending', stage: '', error: null, repo_url: null, doi: null, pid: null, output_dir: null },
      },
    })

    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: /start publishing now/i }))
    await vi.advanceTimersByTimeAsync(2000)
    vi.useRealTimers()

    expect((await screen.findAllByText(/Invalid or unauthorized HuggingFace Hub token\./)).length).toBeGreaterThan(0)
    expect(screen.queryByText('All done!')).not.toBeInTheDocument()
  })

  it('shows an "All done!" screen once the only selected repository finishes publishing', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureHfhAndContinue()
    await screen.findByText('Ready to publish')

    await runHfhPublishToDone()

    await waitFor(() => expect(screen.getByText('All done!')).toBeInTheDocument())
    expect(screen.getByText(/Published to: Hugging Face Hub\./)).toBeInTheDocument()
  })

  it('resets back to the first step when "Publish again" is clicked', async () => {
    render(<WizardPage />)
    await reachPublishStep()

    await userEvent.click(screen.getByRole('button', { name: /hugging face hub/i }))
    await userEvent.click(screen.getByRole('button', { name: /start publishing/i }))
    await configureHfhAndContinue()
    await screen.findByText('Ready to publish')

    await runHfhPublishToDone()
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
