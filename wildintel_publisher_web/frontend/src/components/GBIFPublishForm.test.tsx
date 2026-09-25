import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import GBIFPublishForm, { GBIFSyncDoiSection } from './GBIFPublishForm'

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
    registry_language: 'eng', output_dir: '/gbif/output', has_credentials: false,
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
  it('prefills the environment and registry language from settings', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)

    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    expect(screen.getByLabelText('Registry language')).toHaveValue('eng')
  })

  it('prefills the archive URL from the suggestion, without overwriting a manual edit', async () => {
    const { rerender } = render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    rerender(<GBIFPublishForm suggestedArchiveUrl="https://example.org/datapackage.json" onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Archive URL')).toHaveValue('https://example.org/datapackage.json'))

    rerender(<GBIFPublishForm suggestedArchiveUrl="https://example.org/other.json" onConfigured={vi.fn()} />)
    expect(screen.getByLabelText('Archive URL')).toHaveValue('https://example.org/datapackage.json')
  })

  it('keeps Continue disabled until the required fields are filled', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')
    await userEvent.type(screen.getByLabelText('Installation UUID'), 'inst-1')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('GBIF username'), 'alice')
    await userEvent.type(screen.getByLabelText('GBIF password'), 's3cret')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('warns that the archive is not published yet when Hugging Face Hub precedes GBIF in this run', async () => {
    render(<GBIFPublishForm archiveNotPublishedYet onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByText(/hasn't published yet in this run/i)).toBeInTheDocument()
  })

  it('does not show the not-published-yet warning otherwise', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

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
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByLabelText('Archive URL')).toHaveAttribute('readonly')
    expect(screen.getByText(/Fixed to Hugging Face Hub's own/i)).toBeInTheDocument()
  })

  it('leaves the archive URL editable when not locked', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByLabelText('Archive URL')).not.toHaveAttribute('readonly')
  })

  it('explains the local copy is metadata-only when GBIF is registered standalone', async () => {
    render(<GBIFPublishForm standaloneRegistration onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByText(/the local copy you just fetched/i)).toBeInTheDocument()
  })

  it('does not show the standalone note when Hugging Face Hub is also selected', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.queryByText(/the local copy you just fetched/i)).not.toBeInTheDocument()
  })

  it('explains the archive URL is pending when Zenodo/B2SHARE publish without Hugging Face Hub', async () => {
    render(<GBIFPublishForm pendingFromOtherRepo onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByText(/their own record isn't assigned until they actually upload/i)).toBeInTheDocument()
    expect(screen.queryByText(/the local copy you just fetched/i)).not.toBeInTheDocument()
  })

  it('does not show the pending-from-other-repo note otherwise', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.queryByText(/their own record isn't assigned until they actually upload/i)).not.toBeInTheDocument()
  })

  it('does not require credentials or keys for a dry run', async () => {
    render(<GBIFPublishForm dryRun onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /test connection/i })).not.toBeInTheDocument()
  })

  it('tests the credentials', async () => {
    mockedApi.gbifTestCredentials.mockResolvedValue({ ok: true })
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('GBIF username'), 'alice')
    await userEvent.type(screen.getByLabelText('GBIF password'), 's3cret')
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))

    expect(await screen.findByText('Credentials verified.')).toBeInTheDocument()
    expect(mockedApi.gbifTestCredentials).toHaveBeenCalledWith('alice', 's3cret', 'sandbox')
  })

  it('keeps the Validate archive button disabled until a URL is typed', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByRole('button', { name: /validate archive/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/camtrapdp-remote.zip')
    expect(screen.getByRole('button', { name: /validate archive/i })).toBeEnabled()
  })

  it('validates the archive URL', async () => {
    mockedApi.gbifValidateArchive.mockResolvedValue({ ok: true })
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/camtrapdp-remote.zip')
    await userEvent.click(screen.getByRole('button', { name: /validate archive/i }))

    expect(await screen.findByText('Valid Camtrap DP zip archive.')).toBeInTheDocument()
    expect(mockedApi.gbifValidateArchive).toHaveBeenCalledWith('https://example.org/camtrapdp-remote.zip')
  })

  it('shows an error when the archive is not a valid Camtrap DP zip', async () => {
    mockedApi.gbifValidateArchive.mockRejectedValue(new Error('is not a valid zip archive'))
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.click(screen.getByRole('button', { name: /validate archive/i }))

    expect(await screen.findByText('is not a valid zip archive')).toBeInTheDocument()
  })

  it('resets the archive validation status when the URL is edited', async () => {
    mockedApi.gbifValidateArchive.mockResolvedValue({ ok: true })
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/camtrapdp-remote.zip')
    await userEvent.click(screen.getByRole('button', { name: /validate archive/i }))
    await screen.findByText('Valid Camtrap DP zip archive.')

    await userEvent.type(screen.getByLabelText('Archive URL'), '2')
    expect(screen.queryByText('Valid Camtrap DP zip archive.')).not.toBeInTheDocument()
  })

  it('reports the collected configuration when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    render(<GBIFPublishForm onConfigured={onConfigured} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')
    await userEvent.type(screen.getByLabelText('Installation UUID'), 'inst-1')
    await userEvent.type(screen.getByLabelText('GBIF username'), 'alice')
    await userEvent.type(screen.getByLabelText('GBIF password'), 's3cret')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith({
      archiveUrl: 'https://example.org/datapackage.json', environment: 'sandbox',
      publishingOrganizationKey: 'org-1', installationKey: 'inst-1', registryLanguage: 'eng',
      username: 'alice', password: 's3cret', outputDir: '/gbif/output', datasetKey: '',
    })
  })
})

describe('GBIFPublishForm organization quick-fill', () => {
  it('offers only organizations with a key for the current environment, and fills the UUID on selection', async () => {
    mockedApi.organizations.mockResolvedValue([
      { title: 'WildINTEL', path: 'https://wildintel.eu/', email: null, gbif_sandbox_organization_key: 'sandbox-uuid-1', gbif_production_organization_key: 'prod-uuid-1' },
      { title: 'University of Huelva', path: 'https://www.uhu.es/', email: null, gbif_sandbox_organization_key: null, gbif_production_organization_key: 'prod-uuid-2' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    // University of Huelva has no sandbox key — not offered while sandbox
    // is the selected environment.
    const dropdown = screen.getByLabelText('Publishing organization')
    expect(Array.from(dropdown.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      '— pick a configured organization, or type a UUID below —', 'WildINTEL',
    ])

    await userEvent.selectOptions(dropdown, 'WildINTEL')
    expect(screen.getByLabelText('Publishing organization UUID')).toHaveValue('sandbox-uuid-1')
  })

  it('follows the selected organization across an environment switch, using its own key for the new one', async () => {
    mockedApi.organizations.mockResolvedValue([
      { title: 'WildINTEL', path: 'https://wildintel.eu/', email: null, gbif_sandbox_organization_key: 'sandbox-uuid-1', gbif_production_organization_key: 'prod-uuid-1' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.selectOptions(screen.getByLabelText('Publishing organization'), 'WildINTEL')
    expect(screen.getByLabelText('Publishing organization UUID')).toHaveValue('sandbox-uuid-1')

    await userEvent.selectOptions(screen.getByLabelText('Environment'), 'production')

    expect(screen.getByLabelText('Publishing organization UUID')).toHaveValue('prod-uuid-1')
  })

  it('stops following the selected organization once the UUID is edited by hand', async () => {
    mockedApi.organizations.mockResolvedValue([
      { title: 'WildINTEL', path: 'https://wildintel.eu/', email: null, gbif_sandbox_organization_key: 'sandbox-uuid-1', gbif_production_organization_key: 'prod-uuid-1' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.selectOptions(screen.getByLabelText('Publishing organization'), 'WildINTEL')

    await userEvent.clear(screen.getByLabelText('Publishing organization UUID'))
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'my-own-uuid')
    await userEvent.selectOptions(screen.getByLabelText('Environment'), 'production')

    expect(screen.getByLabelText('Publishing organization UUID')).toHaveValue('my-own-uuid')
  })

  it('hides the dropdown entirely when no organization has a key for either environment', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.queryByLabelText('Publishing organization')).not.toBeInTheDocument()
  })
})

describe('GBIFPublishForm installation quick-fill', () => {
  it('offers only installations with a key for the current environment, and fills the UUID on selection', async () => {
    mockedApi.gbifInstallations.mockResolvedValue([
      { title: 'WildINTEL', sandbox_installation_key: 'sandbox-inst-1', production_installation_key: 'prod-inst-1' },
      { title: 'Another Installation', sandbox_installation_key: null, production_installation_key: 'prod-inst-2' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    // "Another Installation" has no sandbox key — not offered while
    // sandbox is the selected environment.
    const dropdown = screen.getByLabelText('Installation')
    expect(Array.from(dropdown.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      '— pick a configured installation, or type a UUID below —', 'WildINTEL',
    ])

    await userEvent.selectOptions(dropdown, 'WildINTEL')
    expect(screen.getByLabelText('Installation UUID')).toHaveValue('sandbox-inst-1')
  })

  it('follows the selected installation across an environment switch, using its own key for the new one', async () => {
    mockedApi.gbifInstallations.mockResolvedValue([
      { title: 'WildINTEL', sandbox_installation_key: 'sandbox-inst-1', production_installation_key: 'prod-inst-1' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.selectOptions(screen.getByLabelText('Installation'), 'WildINTEL')
    expect(screen.getByLabelText('Installation UUID')).toHaveValue('sandbox-inst-1')

    await userEvent.selectOptions(screen.getByLabelText('Environment'), 'production')

    expect(screen.getByLabelText('Installation UUID')).toHaveValue('prod-inst-1')
  })

  it('stops following the selected installation once the UUID is edited by hand', async () => {
    mockedApi.gbifInstallations.mockResolvedValue([
      { title: 'WildINTEL', sandbox_installation_key: 'sandbox-inst-1', production_installation_key: 'prod-inst-1' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.selectOptions(screen.getByLabelText('Installation'), 'WildINTEL')

    await userEvent.clear(screen.getByLabelText('Installation UUID'))
    await userEvent.type(screen.getByLabelText('Installation UUID'), 'my-own-uuid')
    await userEvent.selectOptions(screen.getByLabelText('Environment'), 'production')

    expect(screen.getByLabelText('Installation UUID')).toHaveValue('my-own-uuid')
  })

  it('hides the dropdown entirely when no installation has a key for either environment', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.queryByLabelText('Installation')).not.toBeInTheDocument()
  })

  it('keeps the organization and installation dropdowns independent of each other', async () => {
    mockedApi.organizations.mockResolvedValue([
      { title: 'Institute of Nature Conservation PAS', path: 'https://www.iop.krakow.pl/', email: null, gbif_sandbox_organization_key: 'org-uuid-1', gbif_production_organization_key: null },
    ])
    mockedApi.gbifInstallations.mockResolvedValue([
      { title: 'WildINTEL', sandbox_installation_key: 'inst-uuid-1', production_installation_key: null },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.selectOptions(screen.getByLabelText('Publishing organization'), 'Institute of Nature Conservation PAS')
    await userEvent.selectOptions(screen.getByLabelText('Installation'), 'WildINTEL')

    expect(screen.getByLabelText('Publishing organization UUID')).toHaveValue('org-uuid-1')
    expect(screen.getByLabelText('Installation UUID')).toHaveValue('inst-uuid-1')
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
  it('keeps "Search existing datasets" disabled until an organization UUID is typed', async () => {
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByRole('button', { name: /search existing datasets/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')
    expect(screen.getByRole('button', { name: /search existing datasets/i })).toBeEnabled()
  })

  it('lists results and fills the dataset UUID when one is picked', async () => {
    mockedApi.gbifOrganizationDatasets.mockResolvedValue([
      { key: 'uuid-1', title: 'Dataset One' },
      { key: 'uuid-2', title: 'Dataset Two' },
    ])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')

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
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')

    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))

    expect(await screen.findByText('No datasets found for this organization yet.')).toBeInTheDocument()
  })

  it('shows an error message when the search itself fails', async () => {
    mockedApi.gbifOrganizationDatasets.mockRejectedValue(new Error('GBIF returned an unexpected error.'))
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')

    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))

    expect(await screen.findByText('GBIF returned an unexpected error.')).toBeInTheDocument()
  })

  it('clears stale results when the organization or environment changes', async () => {
    mockedApi.gbifOrganizationDatasets.mockResolvedValue([{ key: 'uuid-1', title: 'Dataset One' }])
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')
    await userEvent.click(screen.getByRole('button', { name: /search existing datasets/i }))
    await screen.findByText('Dataset One')

    await userEvent.selectOptions(screen.getByLabelText('Environment'), 'production')

    expect(screen.queryByText('Dataset One')).not.toBeInTheDocument()
  })

  it('sends the typed dataset UUID when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    render(<GBIFPublishForm onConfigured={onConfigured} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('Archive URL'), 'https://example.org/datapackage.json')
    await userEvent.type(screen.getByLabelText('Publishing organization UUID'), 'org-1')
    await userEvent.type(screen.getByLabelText('Installation UUID'), 'inst-1')
    await userEvent.type(screen.getByLabelText('Dataset UUID (leave blank to create a new dataset)'), 'existing-uuid')
    await userEvent.type(screen.getByLabelText('GBIF username'), 'alice')
    await userEvent.type(screen.getByLabelText('GBIF password'), 's3cret')
    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith(expect.objectContaining({ datasetKey: 'existing-uuid' }))
  })
})
