import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import type { FetchSession, PreprocessingSession, PublishSessionSummary } from '../types'
import ResumeSessionsPage from './ResumeSessionsPage'

vi.mock('../api', () => ({
  api: {
    discardPublishSession: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const SESSION: PublishSessionSummary = {
  task_id: 'task-1',
  created_at: '2026-09-01T10:00:00Z',
  status: 'error',
  phase: 'publishing',
  product_type: 'camtrapdp',
  source_type: 'trapper',
  dry_run: false,
  input_dir: '/tmp/camtrapdp',
  media_dir: null,
  primary_doi_source: null,
  repos: [
    { repo: 'hfh', repo_id: 'alice/dataset' },
    { repo: 'zenodo', environment: 'sandbox' },
  ],
  repo_status: {
    hfh: { status: 'done', stage: 'done', error: null, repo_url: 'https://huggingface.co/datasets/alice/dataset', doi: null, pid: null, output_dir: '/hfh/output' },
    zenodo: { status: 'error', stage: 'uploading', error: 'network blip', repo_url: null, doi: null, pid: null, output_dir: null },
  },
}

const FETCHING_SESSION: FetchSession = {
  task_id: 'task-2',
  created_at: '2026-09-02T10:00:00Z',
  status: 'error',
  phase: 'fetching',
  product_type: 'camtrapdp',
  source_type: 'trapper',
  error: 'connection reset',
  fetch: {
    source_type: 'trapper', params: { url: 'https://trapper.example.com' }, output_dir: '/tmp/session-2/source', input_dir: null,
  },
}

const PREPROCESSING_SESSION: PreprocessingSession = {
  task_id: 'task-3',
  created_at: '2026-09-03T10:00:00Z',
  status: 'running',
  phase: 'preprocessing',
  product_type: 'camtrapdp',
  source_type: 'archive',
  fetch: {
    source_type: 'archive', params: { url: 'https://example.com/data.zip' }, output_dir: '/tmp/session-3/source', input_dir: '/tmp/session-3/source',
  },
  preprocessing: null,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ResumeSessionsPage', () => {
  it('lists each session with its per-repo status', () => {
    render(<ResumeSessionsPage sessions={[SESSION]} onResume={() => {}} onDiscarded={() => {}} onSkip={() => {}} />)

    expect(screen.getByText('Hugging Face Hub → Zenodo')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Failed: network blip')).toBeInTheDocument()
  })

  it('shows a repo cut off mid-upload (status "running", stage not yet recorded) as interrupted, not "Not started"', () => {
    const session: PublishSessionSummary = {
      ...SESSION,
      repo_status: {
        ...SESSION.repo_status,
        hfh: { status: 'running', stage: '', error: null, repo_url: null, doi: null, pid: null, output_dir: null },
      },
    }
    render(<ResumeSessionsPage sessions={[session]} onResume={() => {}} onDiscarded={() => {}} onSkip={() => {}} />)

    expect(screen.getByText('Interrupted (uploading)')).toBeInTheDocument()
    expect(screen.queryByText('Not started')).not.toBeInTheDocument()
  })

  it('calls onResume with the session when Resume is clicked', async () => {
    const onResume = vi.fn()
    render(<ResumeSessionsPage sessions={[SESSION]} onResume={onResume} onDiscarded={() => {}} onSkip={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: /resume/i }))

    expect(onResume).toHaveBeenCalledWith(SESSION)
  })

  it('discards the session and calls onDiscarded when Discard is clicked', async () => {
    mockedApi.discardPublishSession.mockResolvedValue({ status: 'discarded' })
    const onDiscarded = vi.fn()
    render(<ResumeSessionsPage sessions={[SESSION]} onResume={() => {}} onDiscarded={onDiscarded} onSkip={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: /discard/i }))

    expect(mockedApi.discardPublishSession).toHaveBeenCalledWith('task-1')
    expect(onDiscarded).toHaveBeenCalledWith('task-1')
  })

  it('calls onSkip when starting a new publish instead', async () => {
    const onSkip = vi.fn()
    render(<ResumeSessionsPage sessions={[SESSION]} onResume={() => {}} onDiscarded={() => {}} onSkip={onSkip} />)

    await userEvent.click(screen.getByRole('button', { name: /start a new publish instead/i }))

    expect(onSkip).toHaveBeenCalledOnce()
  })

  it('describes a session still stuck at the fetching phase, with its own error', () => {
    render(<ResumeSessionsPage sessions={[FETCHING_SESSION]} onResume={() => {}} onDiscarded={() => {}} onSkip={() => {}} />)

    expect(screen.getByText('Fetching Camtrap DP from Trapper')).toBeInTheDocument()
    expect(screen.getByText('Failed: connection reset')).toBeInTheDocument()
  })

  it('describes a session stuck at the preprocessing phase', () => {
    render(<ResumeSessionsPage sessions={[PREPROCESSING_SESSION]} onResume={() => {}} onDiscarded={() => {}} onSkip={() => {}} />)

    expect(screen.getByText('Preprocessing Camtrap DP (from a public URL)')).toBeInTheDocument()
    expect(screen.queryByText(/Interrupted$/)).not.toBeInTheDocument()
  })
})
