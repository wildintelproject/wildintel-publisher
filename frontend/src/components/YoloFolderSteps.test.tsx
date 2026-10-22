import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import YoloFolderSteps from './YoloFolderSteps'

vi.mock('../api', () => ({
  api: {
    yoloStructureCheck: vi.fn(), yoloResolveLocalSource: vi.fn(), generateProductMetadata: vi.fn(),
    yoloDeepChecks: vi.fn(), fsPickDirectory: vi.fn(), fsBrowse: vi.fn(),
    reportUrl: (id: string, format: string) => `/api/reports/${id}/download?format=${format}`,
  },
}))
const mockedApi = vi.mocked(api)

const OK = [
  { check: 'data_yaml', label: 'data.yaml found and readable', ok: true, message: 'data.yaml found and valid YAML.' },
  { check: 'classes', label: 'nc matches the declared classes', ok: true, message: 'nc is 2 and 2 classes are declared.' },
]
const result = (over = {}) => ({
  check: 'image_labels', label: 'Every image has a label file', ok: true, message: 'All 3 images have a label file.',
  total: 0, failures: [], truncated: false, failure_message: 'No label file.', ...over,
})

function renderSteps(props = {}) {
  const handlers = { onSelectionChange: vi.fn(), onContinue: vi.fn(), onBack: vi.fn() }
  render(<YoloFolderSteps {...handlers} {...props} />)
  return handlers
}

async function readFolder(path = '/data/yolo') {
  await userEvent.type(screen.getByLabelText('Folder'), path)
  await userEvent.click(screen.getByRole('button', { name: 'Check the structure' }))
}

beforeEach(() => {
  vi.resetAllMocks()
  mockedApi.yoloStructureCheck.mockResolvedValue({ ok: true, checks: OK })
  mockedApi.yoloResolveLocalSource.mockResolvedValue({ status: 'valid', workingDir: '/work', sourceDir: '/data/yolo', taskId: 't1', error: null })
  mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My dataset', authors: [] })
  mockedApi.yoloDeepChecks.mockResolvedValue({ results: [result()], report_id: 'r1' })
})

describe('YoloFolderSteps', () => {
  it('says the original folder is never modified', () => {
    renderSteps()
    expect(screen.getByText(/original folder is never modified/i)).toBeInTheDocument()
  })

  it('reads the structure, lists every requirement and hands over the working copy', async () => {
    const { onSelectionChange } = renderSteps()
    await readFolder()

    expect(await screen.findByText('The YOLO structure was read correctly')).toBeInTheDocument()
    expect(screen.getByText('nc is 2 and 2 classes are declared.')).toBeInTheDocument()
    expect(mockedApi.yoloStructureCheck).toHaveBeenCalledWith('/data/yolo')
    expect(mockedApi.yoloResolveLocalSource).toHaveBeenCalledWith('/data/yolo', undefined)
    await waitFor(() => expect(onSelectionChange).toHaveBeenLastCalledWith({ path: '/work', sourcePath: '/data/yolo', sessionTaskId: 't1' }))
  })

  it('shows what is wrong and does not go on when the structure has problems', async () => {
    mockedApi.yoloStructureCheck.mockResolvedValue({
      ok: false, checks: [{ ...OK[1], ok: false, message: 'nc is 5 but names lists 2 classes.' }],
    })
    renderSteps()
    await readFolder()

    expect(await screen.findByText('The YOLO structure has problems')).toBeInTheDocument()
    expect(screen.getByText('nc is 5 but names lists 2 classes.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue to the checks' })).toBeDisabled()
    expect(mockedApi.yoloResolveLocalSource).not.toHaveBeenCalled()
  })

  it('runs the chosen checks and lets the user continue when they pass', async () => {
    const { onContinue } = renderSteps()
    await readFolder()
    await userEvent.click(await screen.findByRole('button', { name: 'Continue to the checks' }))

    await userEvent.click(screen.getAllByRole('radio', { name: 'Skip' })[0])  // the first check is not run
    await userEvent.click(screen.getByRole('button', { name: 'Run checks' }))

    expect(await screen.findByText('Every check passed.')).toBeInTheDocument()
    expect(screen.getByLabelText('Summary')).toHaveTextContent('Checks run')
    expect(screen.getAllByText('Skipped').length).toBeGreaterThan(0)  // a check with no result is shown as skipped
    expect(mockedApi.yoloDeepChecks).toHaveBeenCalledWith('/work', ['orphan_labels', 'class_use', 'class_ids'])
    expect(screen.getByRole('link', { name: 'Download report' })).toHaveAttribute('href', '/api/reports/r1/download?format=csv')
    await userEvent.click(screen.getByRole('button', { name: 'Continue to the metadata' }))
    expect(onContinue).toHaveBeenCalled()
  })

  it('lists what failed, and blocks a check set to Must pass', async () => {
    mockedApi.yoloDeepChecks.mockResolvedValue({
      report_id: 'r2',
      results: [result({ check: 'class_ids', label: 'Every label uses a declared class', ok: false, message: '1 label line(s) use a class that data.yaml does not declare.', total: 1, failures: ['labels/val/a.txt:2 (class 7)'], failure_message: 'Uses a class id that data.yaml does not declare.' })],
    })
    renderSteps()
    await readFolder()
    await userEvent.click(await screen.findByRole('button', { name: 'Continue to the checks' }))
    await userEvent.click(screen.getByRole('button', { name: 'Run checks' }))

    expect(await screen.findByText(/set to Must pass — resolve it to continue/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue to the metadata' })).toBeDisabled()
    expect(screen.queryByText('labels/val/a.txt:2 (class 7)')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Open the failures of Every label uses a declared class' }))
    expect(screen.getByText('labels/val/a.txt:2 (class 7)')).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('region', { name: /Failures of/ })).getByRole('button', { name: /back/i }))
    expect(screen.queryByText('labels/val/a.txt:2 (class 7)')).not.toBeInTheDocument()
  })

  it('locks the steps that are not reached yet, and offers to edit the ones that are done', async () => {
    renderSteps()
    expect(screen.getAllByRole('img', { name: 'Locked' })).toHaveLength(2)

    await readFolder()
    await userEvent.click(await screen.findByRole('button', { name: 'Continue to the checks' }))

    expect(screen.getAllByRole('img', { name: 'Locked' })).toHaveLength(1)  // only the results are still locked
    expect(screen.getByRole('button', { name: 'Edit Select the folder' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Open / })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Run checks' }))
    await screen.findByText('All 3 images have a label file.')
    expect(screen.queryByRole('img', { name: 'Locked' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit Choose the checks' })).toBeInTheDocument()
  })

  it('goes back to the previous step of the wizard', async () => {
    const { onBack } = renderSteps()
    await userEvent.click(screen.getByRole('button', { name: /back/i }))
    expect(onBack).toHaveBeenCalled()
  })
})
