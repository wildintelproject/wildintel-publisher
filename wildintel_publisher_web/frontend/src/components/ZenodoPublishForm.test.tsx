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
      fitArchiveSize: true, maxZipFile: undefined, minImageEdge: 640,
    })
  })

  it('uses Camtrap DP wording for the Mode section when productType is omitted', async () => {
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    expect(screen.getByText(/bundles them inside Zenodo's own camtrapdp\.zip/i)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^link/i })).toBeInTheDocument()
  })

  it('uses reference-only wording for the Mode section for a Software Application', async () => {
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm productType="software" onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    expect(screen.getByText(/bundles the whole repository/i)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^reference only/i })).toBeInTheDocument()
    expect(screen.queryByText(/camtrapdp\.zip/i)).not.toBeInTheDocument()
  })

  it('shows the archive-size options for Camtrap DP in Mirror mode, and reports them on Continue', async () => {
    const onConfigured = vi.fn()
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm productType="camtrapdp" onOutputDirChange={onOutputDirChange} onConfigured={onConfigured} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    expect(screen.getByText(/resize images to fit the archive size limit/i)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Archive size limit (GiB)'), '10')
    await userEvent.clear(screen.getByLabelText('Minimum image edge (px)'))
    await userEvent.type(screen.getByLabelText('Minimum image edge (px)'), '800')
    await userEvent.type(screen.getByLabelText('Zenodo token'), 'zen_x')

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith(expect.objectContaining({
      fitArchiveSize: true, maxZipFile: 10, minImageEdge: 800,
    }))
  })

  it('hides the archive-size options once Link mode is picked, or for a non-Camtrap-DP product', async () => {
    const onOutputDirChange = vi.fn()
    render(<ZenodoPublishForm productType="camtrapdp" onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/zenodo/output'))

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))
    expect(screen.queryByText(/resize images to fit the archive size limit/i)).not.toBeInTheDocument()

    render(<ZenodoPublishForm productType="yolo" onOutputDirChange={vi.fn()} onConfigured={vi.fn()} />)
    expect(screen.queryByText(/resize images to fit the archive size limit/i)).not.toBeInTheDocument()
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
