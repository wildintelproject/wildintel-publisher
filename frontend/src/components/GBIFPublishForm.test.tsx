import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import GBIFPublishForm, { GBIFSyncDoiSection } from './GBIFPublishForm'
import { OPEN_SETTINGS_EVENT } from './InstancePicker'

// Publishing a new version of something already published — where the existing-record field lives.
const VERSION = { kind: 'version' as const, previous: null }

vi.mock('../api', () => ({
  api: {
    gbifGetConfig: vi.fn(),
    gbifTestCredentials: vi.fn(),
    gbifValidateArchive: vi.fn(),
    gbifSyncDoi: vi.fn(),
    hfhGetConfig: vi.fn(),
    organizations: vi.fn(),
    gbifOrganizationDatasets: vi.fn(),
    gbifInstallations: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.gbifGetConfig.mockResolvedValue({
    environment: 'sandbox', publishing_organization_key: null, installation_key: null,
    keys_by_environment: {
      sandbox: { publishing_organization_key: 'org-1', installation_key: 'inst-1' },
      production: { publishing_organization_key: 'org-2', installation_key: 'inst-2' },
    },
    registry_language: 'eng', output_dir: '/gbif/output', has_credentials: true,
    has_credentials_by_environment: { sandbox: true, production: true },
  })
  mockedApi.hfhGetConfig.mockResolvedValue({
    username: null, output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false,
  })
  // No organizations/installations have a GBIF key configured by default —
  // both quick-fill dropdowns then stay hidden, same as before this
  // feature existed, unless a test opts in with its own mockResolvedValue.
  mockedApi.organizations.mockResolvedValue([])
  mockedApi.gbifInstallations.mockResolvedValue([])
})

describe('GBIFPublishForm', () => {
  it('prefills the environment from settings, and shows the organization and installation saved for it', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)

    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())
    expect(screen.queryByLabelText('Registry language')).not.toBeInTheDocument()
    expect(await screen.findByText('org-1')).toBeInTheDocument()
    expect(screen.getByText('inst-1')).toBeInTheDocument()
    expect(screen.getByText(/sandbox account saved in settings/i)).toBeInTheDocument()
  })

  it('has no account, organization or installation field, and links to the settings', async () => {
    const opened = vi.fn()
    window.addEventListener(OPEN_SETTINGS_EVENT, opened)
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    for (const label of ['GBIF username', 'GBIF password', 'Publishing organization UUID', 'Installation UUID']) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument()
    }
    await userEvent.click(screen.getByRole('button', { name: /open the gbif settings/i }))
    expect(opened).toHaveBeenCalledTimes(1)
    window.removeEventListener(OPEN_SETTINGS_EVENT, opened)
  })

  it('prefills the archive URL from the suggestion, without overwriting a manual edit', async () => {
    const { rerender } = render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    rerender(<GBIFPublishForm publication={VERSION} suggestedArchiveUrl="https://example.org/datapackage.json" onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Archive URL')).toHaveValue('https://example.org/datapackage.json'))

    rerender(<GBIFPublishForm publication={VERSION} suggestedArchiveUrl="https://example.org/other.json" onConfigured={vi.fn()} />)
    expect(screen.getByLabelText('Archive URL')).toHaveValue('https://example.org/datapackage.json')
  })

  it('keeps Continue disabled until an archive URL is given', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('blocks Continue when the settings lack the organization, installation or account of the instance', async () => {
    mockedApi.gbifGetConfig.mockResolvedValue({
      environment: 'sandbox', publishing_organization_key: null, installation_key: null,
      keys_by_environment: {
        sandbox: { publishing_organization_key: null, installation_key: null },
        production: { publishing_organization_key: 'org-2', installation_key: 'inst-2' },
      },
      registry_language: 'eng', output_dir: '/gbif/output', has_credentials: false,
      has_credentials_by_environment: { sandbox: false, production: true },
    })
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeDisabled())
    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')

    expect(screen.getByText('Add a Sandbox account first.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()
  })

  it('warns that the archive is not published yet when Hugging Face Hub precedes GBIF in this run', async () => {
    render(<GBIFPublishForm publication={VERSION} archiveNotPublishedYet onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByText(/hasn't published yet in this run/i)).toBeInTheDocument()
  })

  it('does not show the not-published-yet warning otherwise', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.queryByText(/hasn't published yet in this run/i)).not.toBeInTheDocument()
  })

  it('makes the archive URL read-only when locked to the Hugging Face Hub suggestion', async () => {
    render(
      <GBIFPublishForm
        suggestedArchiveUrl="https://huggingface.co/datasets/alice/dataset/resolve/main/camtrapdp-remote.zip"
        archiveUrlLocked
        onConfigured={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByLabelText('Archive URL')).toHaveAttribute('readonly')
    expect(screen.getByText(/Fixed to Hugging Face Hub's own/i)).toBeInTheDocument()
  })

  it('leaves the archive URL editable when not locked', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByLabelText('Archive URL')).not.toHaveAttribute('readonly')
  })

  it('explains the local copy is metadata-only when GBIF is registered standalone', async () => {
    render(<GBIFPublishForm publication={VERSION} standaloneRegistration onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByText(/the local copy you just fetched/i)).toBeInTheDocument()
  })

  it('does not show the standalone note when Hugging Face Hub is also selected', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.queryByText(/the local copy you just fetched/i)).not.toBeInTheDocument()
  })

  it('explains the archive URL is pending when Zenodo/B2SHARE publish without Hugging Face Hub', async () => {
    render(<GBIFPublishForm publication={VERSION} pendingFromOtherRepo onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByText(/their own record isn't assigned until they actually upload/i)).toBeInTheDocument()
    expect(screen.queryByText(/the local copy you just fetched/i)).not.toBeInTheDocument()
  })

  it('does not show the pending-from-other-repo note otherwise', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.queryByText(/their own record isn't assigned until they actually upload/i)).not.toBeInTheDocument()
  })

  it('does not require credentials or keys for a dry run', async () => {
    render(<GBIFPublishForm publication={VERSION} dryRun onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /test connection/i })).not.toBeInTheDocument()
  })

  it('keeps the Validate archive button disabled until a URL is typed', async () => {
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByRole('button', { name: /validate archive/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/camtrapdp-remote.zip')
    expect(screen.getByRole('button', { name: /validate archive/i })).toBeEnabled()
  })

  it('validates the archive URL', async () => {
    mockedApi.gbifValidateArchive.mockResolvedValue({ ok: true })
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/camtrapdp-remote.zip')
    await userEvent.click(screen.getByRole('button', { name: /validate archive/i }))

    expect(await screen.findByText('Valid Camtrap DP zip archive.')).toBeInTheDocument()
    expect(mockedApi.gbifValidateArchive).toHaveBeenCalledWith('https://example.org/camtrapdp-remote.zip')
  })

  it('shows an error when the archive is not a valid Camtrap DP zip', async () => {
    mockedApi.gbifValidateArchive.mockRejectedValue(new Error('is not a valid zip archive'))
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.click(screen.getByRole('button', { name: /validate archive/i }))

    expect(await screen.findByText('is not a valid zip archive')).toBeInTheDocument()
  })

  it('resets the archive validation status when the URL is edited', async () => {
    mockedApi.gbifValidateArchive.mockResolvedValue({ ok: true })
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/camtrapdp-remote.zip')
    await userEvent.click(screen.getByRole('button', { name: /validate archive/i }))
    await screen.findByText('Valid Camtrap DP zip archive.')

    await userEvent.type(screen.getByLabelText('Archive URL'), '2')
    expect(screen.queryByText('Valid Camtrap DP zip archive.')).not.toBeInTheDocument()
  })

  it('reports the collected configuration when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    render(<GBIFPublishForm publication={VERSION} onConfigured={onConfigured} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith({
      archiveUrl: 'https://example.org/datapackage.json', environment: 'sandbox',
      publishingOrganizationKey: 'org-1', installationKey: 'inst-1', registryLanguage: 'eng',
      username: '', password: '', outputDir: '/gbif/output', datasetKey: '',
    })
  })
})

describe('GBIFSyncDoiSection', () => {
  it('prefills the Hugging Face Hub export directory and username from settings', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false,
    })
    render(<GBIFSyncDoiSection gbifOutputDir="/gbif/output" />)

    await waitFor(() => expect(screen.getByText('/hfh/output')).toBeInTheDocument())
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
  })

  it('syncs the DOI and shows the resulting repo URL', async () => {
    mockedApi.gbifSyncDoi.mockResolvedValue({ doi: '10.21373/eet8jz', repo_url: 'https://huggingface.co/datasets/alice/dataset' })
    render(<GBIFSyncDoiSection gbifOutputDir="/gbif/output" />)
    await waitFor(() => expect(screen.getByText('/hfh/output')).toBeInTheDocument())

    await userEvent.clear(screen.getByLabelText('User or organization'))
    await userEvent.type(screen.getByLabelText('User or organization'), 'alice')
    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('button', { name: /^sync doi$/i }))

    expect(await screen.findByText('https://huggingface.co/datasets/alice/dataset')).toBeInTheDocument()
    expect(mockedApi.gbifSyncDoi).toHaveBeenCalledWith({
      gbifOutputDir: '/gbif/output', hfhOutputDir: '/hfh/output', hfhRepoId: 'alice/dataset', hfhToken: 'hf_x',
    })
  })

  it('shows an error if the sync fails', async () => {
    mockedApi.gbifSyncDoi.mockRejectedValue(new Error('has no DOI'))
    render(<GBIFSyncDoiSection gbifOutputDir="/gbif/output" />)
    await waitFor(() => expect(screen.getByText('/hfh/output')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('User or organization'), 'alice')
    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('button', { name: /^sync doi$/i }))

    expect(await screen.findByText('has no DOI')).toBeInTheDocument()
  })
})

describe('GBIFPublishForm dataset picker', () => {
  it('keeps "Search existing datasets" disabled while the instance has no publishing organization saved', async () => {
    mockedApi.gbifGetConfig.mockResolvedValue({
      environment: 'sandbox', publishing_organization_key: null, installation_key: null,
      keys_by_environment: {
        sandbox: { publishing_organization_key: null, installation_key: null },
        production: { publishing_organization_key: null, installation_key: null },
      },
      registry_language: 'eng', output_dir: '/gbif/output', has_credentials: true,
      has_credentials_by_environment: { sandbox: true, production: true },
    })
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByRole('button', { name: /search existing datasets/i })).toBeDisabled()
  })

  it('lists results and fills the dataset UUID when one is picked', async () => {
    mockedApi.gbifOrganizationDatasets.mockResolvedValue([
      { key: 'uuid-1', title: 'Dataset One' },
      { key: 'uuid-2', title: 'Dataset Two' },
    ])
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))

    expect(mockedApi.gbifOrganizationDatasets).toHaveBeenCalledWith('org-1', 'sandbox')
    await screen.findByText('Dataset One')
    expect(screen.getByText('Dataset Two')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Dataset One'))

    expect(screen.getByLabelText('Dataset UUID (leave blank to create a new dataset)')).toHaveValue('uuid-1')
    // The results list collapses once a pick is made.
    expect(screen.queryByText('Dataset Two')).not.toBeInTheDocument()
  })

  it('reports no datasets found instead of an empty, silent list', async () => {
    mockedApi.gbifOrganizationDatasets.mockResolvedValue([])
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))

    expect(await screen.findByText('No datasets found for this organization yet.')).toBeInTheDocument()
  })

  it('shows an error message when the search itself fails', async () => {
    mockedApi.gbifOrganizationDatasets.mockRejectedValue(new Error('GBIF returned an unexpected error.'))
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))

    expect(await screen.findByText('GBIF returned an unexpected error.')).toBeInTheDocument()
  })

  it('clears stale results when the organization or environment changes', async () => {
    mockedApi.gbifOrganizationDatasets.mockResolvedValue([{ key: 'uuid-1', title: 'Dataset One' }])
    render(<GBIFPublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())
    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))
    await screen.findByText('Dataset One')

    await userEvent.click(screen.getByRole('radio', { name: /^production/i }))

    expect(screen.queryByText('Dataset One')).not.toBeInTheDocument()
  })

  it('sends the typed dataset UUID when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    render(<GBIFPublishForm publication={VERSION} onConfigured={onConfigured} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.type(screen.getByLabelText('Dataset UUID (leave blank to create a new dataset)'), 'existing-uuid')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith(expect.objectContaining({ datasetKey: 'existing-uuid' }))
  })
})


describe('GBIFPublishForm new dataset vs. new version', () => {
  it('pre-fills and requires the previous version\'s own GBIF dataset', async () => {
    const previous = {
      title: 'T', version: '3.0', warnings: [],
      gbif: { dataset_key: 'uuid-9', environment: 'sandbox' as const, url: 'https://registry.gbif-test.org/dataset/uuid-9' },
    }
    render(<GBIFPublishForm publication={{ kind: 'version', previous }} onConfigured={vi.fn()} />)

    expect(await screen.findByLabelText(/previous version's gbif dataset uuid/i)).toHaveValue('uuid-9')
    expect(screen.getByText(/updates that same gbif dataset/i)).toBeInTheDocument()
  })

  it('hides the existing-dataset field for a new dataset', async () => {
    render(<GBIFPublishForm publication={{ kind: 'new', previous: null }} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.queryByLabelText(/dataset uuid/i)).not.toBeInTheDocument()
  })
})
