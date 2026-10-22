import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import B2SharePublishForm, { SyncPidSection } from './B2SharePublishForm'

// Publishing a new version of something already published — where the existing-record field lives.
const VERSION = { kind: 'version' as const, previous: null }

vi.mock('../api', () => ({
  api: {
    b2shareGetConfig: vi.fn(),
    b2shareTestToken: vi.fn(),
    b2shareRecords: vi.fn(),
    b2shareSyncPid: vi.fn(),
    hfhGetConfig: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.b2shareGetConfig.mockResolvedValue({
    environment: 'sandbox', community_id: null, community_id_by_environment: { sandbox: 'uuid-1', production: 'uuid-2' }, output_dir: '/b2share/output', version: '1.0', timeout: 60, has_token: true, has_token_by_environment: { sandbox: true, production: true },
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
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)

    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))
    expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked()
  })

  it('shows a note that the linked HFH repository is detected automatically, in link mode — no field to type it in', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.queryByText(/detected automatically/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    expect(screen.getByText(/detected automatically/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('HFH user or organization')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('HFH repository name')).not.toBeInTheDocument()
  })

  it('has no token or community field, and links to the settings', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.queryByLabelText('B2SHARE token')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Community UUID')).not.toBeInTheDocument()
    expect(screen.getByText('uuid-1')).toBeInTheDocument()
    expect(screen.getByText(/sandbox token saved in settings/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open the b2share settings/i })).toBeInTheDocument()
  })

  it('needs a community saved in the settings for the selected instance, even in mirror mode', async () => {
    mockedApi.b2shareGetConfig.mockResolvedValue({
      environment: 'sandbox', community_id: null, community_id_by_environment: { sandbox: null, production: 'uuid-2' }, output_dir: '/b2share/output', version: '1.0', timeout: 60, has_token: true, has_token_by_environment: { sandbox: true, production: true },
    })
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.getByText(/no community is saved for sandbox yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.click(screen.getByRole('radio', { name: /^production/i }))
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('disables an instance whose token is missing in the settings', async () => {
    mockedApi.b2shareGetConfig.mockResolvedValue({
      environment: 'sandbox', community_id: null, community_id_by_environment: { sandbox: 'uuid-1', production: null }, output_dir: '/b2share/output', version: '1.0', timeout: 60, has_token: true, has_token_by_environment: { sandbox: true, production: false },
    })
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.getByRole('radio', { name: /^production/i })).toBeDisabled()
    expect(screen.getByText('Add a Production token first.')).toBeInTheDocument()
  })

  it('reports the collected configuration when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={onConfigured} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith({
      token: '', environment: 'sandbox', communityId: 'uuid-1',
      mirrorImages: false, outputMode: 'prepared', outputDir: '/b2share/output',
      fitArchiveSize: true, maxZipFile: undefined, minImageEdge: 640,
      existingRecordId: '',
    })
  })

  it('keeps "Search existing records" disabled while the environment has no saved token', async () => {
    mockedApi.b2shareGetConfig.mockResolvedValue({
      environment: 'sandbox', community_id: null, community_id_by_environment: { sandbox: 'uuid-1', production: null }, output_dir: '/b2share/output', version: '1.0', timeout: 60, has_token: false, has_token_by_environment: { sandbox: false, production: false },
    })
    render(<B2SharePublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    expect(screen.getByRole('button', { name: /search existing records/i })).toBeDisabled()
  })

  it('lists results and fills the record id when one is picked', async () => {
    mockedApi.b2shareRecords.mockResolvedValue([
      { id: 'rec-1', title: 'Camera Trap Survey v1' },
      { id: 'rec-2', title: 'Camera Trap Survey v2' },
    ])
    render(<B2SharePublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.click(screen.getByRole('button', { name: /search existing records/i }))

    expect(mockedApi.b2shareRecords).toHaveBeenCalledWith('sandbox', '')
    await screen.findByText('Camera Trap Survey v1')
    expect(screen.getByText('Camera Trap Survey v2')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Camera Trap Survey v1'))

    expect(screen.getByLabelText('B2SHARE record ID (leave blank to create a new draft)')).toHaveValue('rec-1')
    // The results list collapses once a pick is made.
    expect(screen.queryByText('Camera Trap Survey v2')).not.toBeInTheDocument()
  })

  it('reports no records found instead of an empty, silent list', async () => {
    mockedApi.b2shareRecords.mockResolvedValue([])
    render(<B2SharePublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.click(screen.getByRole('button', { name: /search existing records/i }))

    expect(await screen.findByText('No published records found yet.')).toBeInTheDocument()
  })

  it('shows an error message when the search itself fails', async () => {
    mockedApi.b2shareRecords.mockRejectedValue(new Error('B2SHARE returned an unexpected error.'))
    render(<B2SharePublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())

    await userEvent.click(screen.getByRole('button', { name: /search existing records/i }))

    expect(await screen.findByText('B2SHARE returned an unexpected error.')).toBeInTheDocument()
  })

  it('clears stale results when the environment changes', async () => {
    mockedApi.b2shareRecords.mockResolvedValue([{ id: 'rec-1', title: 'Camera Trap Survey v1' }])
    render(<B2SharePublishForm publication={VERSION} onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())
    await userEvent.click(screen.getByRole('button', { name: /search existing records/i }))
    await screen.findByText('Camera Trap Survey v1')

    await userEvent.click(screen.getByRole('radio', { name: /^production/i }))

    expect(screen.queryByText('Camera Trap Survey v1')).not.toBeInTheDocument()
  })

  it('sends the typed existing record id when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onConfigured={onConfigured} />)
    await waitFor(() => expect(screen.getByRole('radio', { name: /^sandbox/i })).toBeChecked())
    await userEvent.type(
      screen.getByLabelText('B2SHARE record ID (leave blank to create a new draft)'), 'rec-old',
    )

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith(expect.objectContaining({ existingRecordId: 'rec-old' }))
  })

  it('uses Camtrap DP wording for the Mode section when productType is omitted', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.getByText(/bundles them inside B2SHARE's own camtrapdp\.zip/i)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^link/i })).toBeInTheDocument()
  })

  it('uses reference-only wording for the Mode section for a Software Application', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} productType="software" onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.getByText(/bundles the whole repository/i)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^reference only/i })).toBeInTheDocument()
    expect(screen.queryByText(/camtrapdp\.zip/i)).not.toBeInTheDocument()
  })

  it('shows the archive-size options for Camtrap DP in Mirror mode, and reports them on Continue', async () => {
    const onConfigured = vi.fn()
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} productType="camtrapdp" onOutputDirChange={onOutputDirChange} onConfigured={onConfigured} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    expect(screen.getByText(/resize images to fit the archive size limit/i)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Archive size limit (GiB)'), '5')
    await userEvent.clear(screen.getByLabelText('Minimum image edge (px)'))
    await userEvent.type(screen.getByLabelText('Minimum image edge (px)'), '800')

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith(expect.objectContaining({
      fitArchiveSize: true, maxZipFile: 5, minImageEdge: 800,
    }))
  })

  it('hides the archive-size options once Link mode is picked, or for a non-Camtrap-DP product', async () => {
    const onOutputDirChange = vi.fn()
    render(<B2SharePublishForm publication={VERSION} productType="camtrapdp" onOutputDirChange={onOutputDirChange} onConfigured={vi.fn()} />)
    await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/b2share/output'))

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))
    expect(screen.queryByText(/resize images to fit the archive size limit/i)).not.toBeInTheDocument()

    render(<B2SharePublishForm publication={VERSION} productType="yolo" onOutputDirChange={vi.fn()} onConfigured={vi.fn()} />)
    expect(screen.queryByText(/resize images to fit the archive size limit/i)).not.toBeInTheDocument()
  })
})

describe('SyncPidSection', () => {
  it('prefills the HFH export directory/username from settings, and syncs the PID once the repository name is given', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.b2shareSyncPid.mockResolvedValue({ pid: '10.5072/b2share.123', repo_url: 'https://huggingface.co/datasets/alice/dataset' })
    render(<SyncPidSection initialRecordId="1234" />)

    await screen.findByDisplayValue('alice')
    expect(screen.getByLabelText('User or organization')).toHaveValue('alice')
    expect(screen.getByLabelText('Repository name')).toHaveValue('') // not remembered — the dataset name is per-product

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync pid\/doi$/i }))

    const link = await screen.findByRole('link', { name: /huggingface\.co\/datasets\/alice\/dataset/i })
    expect(link.parentElement?.textContent).toContain('PID/DOI synced to')
    expect(mockedApi.b2shareSyncPid).toHaveBeenCalledWith({
      environment: 'sandbox', recordId: '1234', hfhRepoId: 'alice/dataset', hfhToken: '',
    })
  })

  it('shows a warning when nothing could be synced yet', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.b2shareSyncPid.mockResolvedValue({ pid: null, repo_url: 'https://huggingface.co/datasets/alice/dataset' })
    render(<SyncPidSection initialRecordId="1234" />)
    await screen.findByDisplayValue('alice')

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync pid\/doi$/i }))

    expect(await screen.findByText(/nothing was synced/i)).toBeInTheDocument()
  })

  it('shows an error if the sync fails', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    mockedApi.b2shareSyncPid.mockRejectedValue(new Error('The B2SHARE record is not prepared yet.'))
    render(<SyncPidSection initialRecordId="1234" />)
    await screen.findByDisplayValue('alice')

    await userEvent.type(screen.getByLabelText('Repository name'), 'dataset')
    await userEvent.click(screen.getByRole('button', { name: /^sync pid\/doi$/i }))

    expect(await screen.findByText('The B2SHARE record is not prepared yet.')).toBeInTheDocument()
  })
})
