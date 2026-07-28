import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import ZenodoPublishForm, { SyncDoiSection } from './ZenodoPublishForm'

vi.mock('../api', () => ({
  api: {
    zenodoGetConfig: vi.fn(),
    zenodoTestToken: vi.fn(),
    zenodoSyncDoi: vi.fn(),
    hfhGetConfig: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.zenodoGetConfig.mockResolvedValue({
    environment: 'sandbox', communities: null, output_dir: '/zenodo/output', version: '1.0', timeout: 60, has_token: false,
  })
  mockedApi.hfhGetConfig.mockResolvedValue({
    username: null, output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ZenodoPublishForm', () => {
  it('prefills the output directory and environment from settings', async () => {
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)

    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))
    expect(screen.getByLabelText('Environment')).toHaveValue('sandbox')
  })

  it('shows a note that the linked HFH repository is detected automatically, in link mode', async () => {
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    expect(screen.queryByText(/detected automatically/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    expect(screen.getByText(/detected automatically/i)).toBeInTheDocument()
    // no manual field for it — fully automatic, same principle as B2SharePublishForm
    expect(screen.queryByLabelText('HFH user or organization')).not.toBeInTheDocument()
  })

  it('enables Continue once a token is given, regardless of mode', async () => {
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))
    // still enabled — the HFH repository is resolved later, not required here
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('tests the token', async () => {
    mockedApi.zenodoTestToken.mockResolvedValue({ ok: true })
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))

    expect(await screen.findByText('Token verified.')).toBeInTheDocument()
    expect(mockedApi.zenodoTestToken).toHaveBeenCalledWith('zen_x', 'sandbox')
  })

  it('reports the collected configuration when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm onOutputDirChange={onOutputDirChange} onConfigured={onConfigured} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')
    await userEvent.type(screen.getByLabelText('Communities'), 'wildintel')
    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith({
      token: 'zen_x', environment: 'sandbox', communities: 'wildintel',
      mirrorImages: false, outputMode: 'prepared', outputDir: '/zenodo/output',
    })
  })
})

describe('SyncDoiSection', () => {
  it('prefills the HFH export directory/username from settings, and syncs the DOI once the repository name is given', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.zenodoSyncDoi.mockResolvedValue({ doi: '10.5281/zenodo.123', repo_url: 'https://huggingface.co/datasets/alice/dataset' })
    render(<SyncDoiSection zenodoOutputDir="/zenodo/output" />)

    await screen.findByText('/hfh/output')
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
    expect(screen.getByLabelText('Repository name')).toHaveValue('') // not remembered — the dataset name is per-product

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync doi$/i }))

    const link = await screen.findByRole('link', { name: /huggingface\.co\/datasets\/alice\/dataset/i })
    expect(link.parentElement?.textContent).toContain('DOI synced to')
    expect(mockedApi.zenodoSyncDoi).toHaveBeenCalledWith({
      zenodoOutputDir: '/zenodo/output', hfhOutputDir: '/hfh/output', hfhRepoId: 'alice/dataset', hfhToken: '',
    })
  })

  it('shows an error if the sync fails', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.zenodoSyncDoi.mockRejectedValue(new Error('The Zenodo deposition is not published yet.'))
    render(<SyncDoiSection zenodoOutputDir="/zenodo/output" />)
    await screen.findByText('/hfh/output')

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync doi$/i }))

    expect(await screen.findByText('The Zenodo deposition is not published yet.')).toBeInTheDocument()
  })
})
