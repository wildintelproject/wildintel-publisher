import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import B2SharePublishForm, { SyncPidSection } from './B2SharePublishForm'

vi.mock('../api', () => ({
  api: {
    b2shareGetConfig: vi.fn(),
    b2shareTestToken: vi.fn(),
    b2shareSyncPid: vi.fn(),
    hfhGetConfig: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.b2shareGetConfig.mockResolvedValue({
    environment: 'sandbox', community_id: null, output_dir: '/b2share/output', version: '1.0', timeout: 60, has_token: false,
  })
  mockedApi.hfhGetConfig.mockResolvedValue({
    username: null, output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('B2SharePublishForm', () => {
  it('prefills the output directory and environment from settings', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)

    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))
    expect(screen.getByLabelText('Environment')).toHaveValue('sandbox')
  })

  it('shows a note that the linked HFH repository is detected automatically, in link mode — no field to type it in', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.queryByText(/detected automatically/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    expect(screen.getByText(/detected automatically/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('HFH user or organization')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('HFH repository name')).not.toBeInTheDocument()
  })

  it('requires a community UUID even in mirror mode', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    await userEvent.type(screen.getByLabelText('B2SHARE token'), 'b2_x')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Community UUID'), 'uuid-1')
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('allows continuing in link mode even without a community UUID filled in yet being irrelevant to detection', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    await userEvent.type(screen.getByLabelText('B2SHARE token'), 'b2_x')
    await userEvent.type(screen.getByLabelText('Community UUID'), 'uuid-1')
    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('tests the token', async () => {
    mockedApi.b2shareTestToken.mockResolvedValue({ ok: true })
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    await userEvent.type(screen.getByLabelText('B2SHARE token'), 'b2_x')
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))

    expect(await screen.findByText('Token verified.')).toBeInTheDocument()
    expect(mockedApi.b2shareTestToken).toHaveBeenCalledWith('b2_x', 'sandbox')
  })

  it('reports the collected configuration when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm onOutputDirChange={onOutputDirChange} onConfigured={onConfigured} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    await userEvent.type(screen.getByLabelText('B2SHARE token'), 'b2_x')
    await userEvent.type(screen.getByLabelText('Community UUID'), 'uuid-1')
    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith({
      token: 'b2_x', environment: 'sandbox', communityId: 'uuid-1',
      mirrorImages: false, outputMode: 'prepared', outputDir: '/b2share/output',
    })
  })
})

describe('SyncPidSection', () => {
  it('prefills the HFH export directory/username from settings, and syncs the PID once the repository name is given', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.b2shareSyncPid.mockResolvedValue({ pid: '10.5072/b2share.123', repo_url: 'https://huggingface.co/datasets/alice/dataset' })
    render(<SyncPidSection b2shareOutputDir="/b2share/output" />)

    await screen.findByText('/hfh/output')
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
    expect(screen.getByLabelText('Repository name')).toHaveValue('') // not remembered — the dataset name is per-product

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync pid\/doi$/i }))

    const link = await screen.findByRole('link', { name: /huggingface\.co\/datasets\/alice\/dataset/i })
    expect(link.parentElement?.textContent).toContain('PID/DOI synced to')
    expect(mockedApi.b2shareSyncPid).toHaveBeenCalledWith({
      b2shareOutputDir: '/b2share/output', hfhOutputDir: '/hfh/output', hfhRepoId: 'alice/dataset', hfhToken: '',
    })
  })

  it('shows a warning when nothing could be synced yet', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.b2shareSyncPid.mockResolvedValue({ pid: null, repo_url: 'https://huggingface.co/datasets/alice/dataset' })
    render(<SyncPidSection b2shareOutputDir="/b2share/output" />)
    await screen.findByText('/hfh/output')

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync pid\/doi$/i }))

    expect(await screen.findByText(/nothing was synced/i)).toBeInTheDocument()
  })

  it('shows an error if the sync fails', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.b2shareSyncPid.mockRejectedValue(new Error('The B2SHARE record is not prepared yet.'))
    render(<SyncPidSection b2shareOutputDir="/b2share/output" />)
    await screen.findByText('/hfh/output')

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync pid\/doi$/i }))

    expect(await screen.findByText('The B2SHARE record is not prepared yet.')).toBeInTheDocument()
  })
})
