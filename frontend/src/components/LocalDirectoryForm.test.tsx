import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import LocalDirectoryForm from './LocalDirectoryForm'

vi.mock('../api', () => ({
  api: {
    generateProductMetadata: vi.fn(),
    resolveLocalSource: vi.fn(),
    fsBrowse: vi.fn(),
    fsPickDirectory: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

function renderForm(onSelectionChange = vi.fn()) {
  render(<LocalDirectoryForm productType="camtrapdp" onSelectionChange={onSelectionChange} />)
  return onSelectionChange
}

describe('LocalDirectoryForm', () => {
  it('reports the working dir (and original path) once metadata.json is generated successfully', async () => {
    mockedApi.resolveLocalSource.mockResolvedValue({
      status: 'valid', workingDir: '/app/local-source/abc123', sourceDir: '/data/camtrapdp', taskId: 'session-1', error: null,
    })
    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Camtrap DP', authors: [] })
    const onSelectionChange = renderForm()

    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')

    await waitFor(() => expect(screen.getByText('My Camtrap DP')).toBeInTheDocument())
    expect(mockedApi.resolveLocalSource).toHaveBeenLastCalledWith('/data/camtrapdp', undefined)
    expect(mockedApi.generateProductMetadata).toHaveBeenLastCalledWith(
      '/app/local-source/abc123', 'camtrapdp', undefined, undefined, undefined, undefined, 'session-1',
    )
    expect(onSelectionChange).toHaveBeenLastCalledWith({
      path: '/app/local-source/abc123', sourcePath: '/data/camtrapdp', sessionTaskId: 'session-1',
    })
  })

  it('reuses the same session on a later resolve instead of minting a new one', async () => {
    mockedApi.resolveLocalSource.mockResolvedValue({
      status: 'valid', workingDir: '/app/local-source/abc123', sourceDir: '/data/camtrapdp', taskId: 'session-1', error: null,
    })
    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Camtrap DP', authors: [] })
    renderForm()

    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')
    await waitFor(() => expect(screen.getByText('My Camtrap DP')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Directory'), '2')
    await waitFor(() => expect(mockedApi.resolveLocalSource).toHaveBeenLastCalledWith('/data/camtrapdp2', 'session-1'))
  })

  it('shows an error and does not report a selection when the directory is not a valid Camtrap DP', async () => {
    mockedApi.resolveLocalSource.mockResolvedValue({
      status: 'invalid', workingDir: null, sourceDir: '/not/a/camtrapdp', taskId: 'session-2', error: 'datapackage.json not found.',
    })
    const onSelectionChange = renderForm()

    await userEvent.type(screen.getByLabelText('Directory'), '/not/a/camtrapdp')

    await waitFor(() => expect(screen.getByText('datapackage.json not found.')).toBeInTheDocument())
    expect(onSelectionChange).toHaveBeenLastCalledWith(null)
  })

  it('opens the operating system\'s own folder dialog when Browse is clicked, and fills in the chosen path', async () => {
    mockedApi.fsPickDirectory.mockResolvedValue({ path: '/data/yolo' })
    renderForm()

    await userEvent.click(screen.getByRole('button', { name: /browse/i }))

    await waitFor(() => expect(screen.getByLabelText('Directory')).toHaveValue('/data/yolo'))
    expect(mockedApi.fsPickDirectory).toHaveBeenCalled()
    expect(screen.queryByText('Select the directory')).not.toBeInTheDocument()
  })

  it('leaves the path alone when the native dialog is cancelled', async () => {
    mockedApi.fsPickDirectory.mockResolvedValue({ path: null })
    renderForm()
    await userEvent.type(screen.getByLabelText('Directory'), '/keep/me')

    await userEvent.click(screen.getByRole('button', { name: /browse/i }))

    await waitFor(() => expect(mockedApi.fsPickDirectory).toHaveBeenCalledWith('/keep/me', 'Select the directory'))
    expect(screen.getByLabelText('Directory')).toHaveValue('/keep/me')
  })

  it('falls back to the in-page directory picker when this machine has no native dialog', async () => {
    mockedApi.fsPickDirectory.mockRejectedValue(new Error('No native folder dialog available'))
    mockedApi.fsBrowse.mockResolvedValue({ current: '/home/user', parent: '/home', dirs: [] })
    renderForm()

    await userEvent.click(screen.getByRole('button', { name: /browse/i }))

    expect(await screen.findByText('Select the directory')).toBeInTheDocument()
  })
})
