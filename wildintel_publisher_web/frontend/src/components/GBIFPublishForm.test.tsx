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
      username: 'alice', password: 's3cret', outputDir: '/gbif/output',
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
