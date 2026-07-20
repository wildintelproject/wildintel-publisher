import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import LocalDirectoryForm from './LocalDirectoryForm'

vi.mock('../api', () => ({
  api: {
    generateProductMetadata: vi.fn(),
    fsBrowse: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

function renderForm(onSelectionChange = vi.fn()) {
  render(<LocalDirectoryForm productType="camtrapdp" onSelectionChange={onSelectionChange} />)
  return onSelectionChange
}

describe('LocalDirectoryForm', () => {
  it('reports the path once metadata.json is generated successfully', async () => {
    mockedApi.generateProductMetadata.mockResolvedValue({ title: 'My Camtrap DP', authors: [] })
    const onSelectionChange = renderForm()

    await userEvent.type(screen.getByLabelText('Directory'), '/data/camtrapdp')

    await waitFor(() => expect(screen.getByText('My Camtrap DP')).toBeInTheDocument())
    expect(onSelectionChange).toHaveBeenLastCalledWith('/data/camtrapdp')
    expect(mockedApi.generateProductMetadata).toHaveBeenLastCalledWith('/data/camtrapdp', 'camtrapdp')
  })

  it('shows an error and does not report a selection when the directory is invalid', async () => {
    mockedApi.generateProductMetadata.mockRejectedValue(new Error('datapackage.json not found.'))
    const onSelectionChange = renderForm()

    await userEvent.type(screen.getByLabelText('Directory'), '/not/a/camtrapdp')

    await waitFor(() => expect(screen.getByText('datapackage.json not found.')).toBeInTheDocument())
    expect(onSelectionChange).toHaveBeenLastCalledWith(null)
  })

  it('opens the directory picker when Browse is clicked', async () => {
    mockedApi.fsBrowse.mockResolvedValue({ current: '/home/user', parent: '/home', dirs: [] })
    renderForm()

    await userEvent.click(screen.getByRole('button', { name: /browse/i }))

    expect(await screen.findByText('Select the directory')).toBeInTheDocument()
  })
})
