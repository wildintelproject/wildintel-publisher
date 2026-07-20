import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import GBIFPublishForm from './GBIFPublishForm'

vi.mock('../api', () => ({
  api: {
    gbifGetConfig: vi.fn(),
    gbifTestCredentials: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.gbifGetConfig.mockResolvedValue({
    environment: 'sandbox', publishing_organization_key: null, installation_key: null,
    registry_language: 'eng', output_dir: '/gbif/output', has_credentials: false,
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

  it('does not require credentials or keys for a dry run', async () => {
    render(<GBIFPublishForm dryRun onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /test credentials/i })).not.toBeInTheDocument()
  })

  it('tests the credentials', async () => {
    mockedApi.gbifTestCredentials.mockResolvedValue({ ok: true })
    render(<GBIFPublishForm onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Environment')).toHaveValue('sandbox'))

    await userEvent.type(screen.getByLabelText('GBIF username'), 'alice')
    await userEvent.type(screen.getByLabelText('GBIF password'), 's3cret')
    await userEvent.click(screen.getByRole('button', { name: /test credentials/i }))

    expect(await screen.findByText('Credentials verified.')).toBeInTheDocument()
    expect(mockedApi.gbifTestCredentials).toHaveBeenCalledWith('alice', 's3cret', 'sandbox')
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
