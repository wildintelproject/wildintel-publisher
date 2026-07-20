import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import CompleteMetadataForm from './CompleteMetadataForm'
import type { DatapackageSummary } from '../types'

vi.mock('../api', () => ({
  api: {
    completeProductMetadata: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const partialSummary: DatapackageSummary = {
  product_type: 'camtrapdp',
  title: 'My Dataset',
  description: undefined,
  version: undefined,
  license: null,
  authors: [],
  homepage: null,
}

describe('CompleteMetadataForm', () => {
  it('shows the already-known fields as read-only and the missing ones as editable', () => {
    render(<CompleteMetadataForm inputDir="/data/camtrapdp" summary={partialSummary} onComplete={vi.fn()} />)

    expect(screen.getByText('My Dataset')).toBeInTheDocument()
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument()

    expect(screen.getByLabelText('Description')).toBeInTheDocument()
    expect(screen.getByLabelText('Version')).toBeInTheDocument()
    expect(screen.getByLabelText('License ID')).toBeInTheDocument()
  })

  it('keeps Continue disabled until every required field has a value', async () => {
    render(<CompleteMetadataForm inputDir="/data/camtrapdp" summary={partialSummary} onComplete={vi.fn()} />)

    const continueButton = screen.getByRole('button', { name: /continue/i })
    expect(continueButton).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Description'), 'A test dataset.')
    await userEvent.type(screen.getByLabelText('Version'), '1.0')
    await userEvent.type(screen.getByLabelText('License ID'), 'CC-BY-4.0')
    await userEvent.type(screen.getByLabelText('License name'), 'CC BY 4.0')
    expect(continueButton).toBeDisabled() // still no author name

    await userEvent.type(screen.getByLabelText('Author 1 name'), 'Alice')
    expect(continueButton).toBeEnabled()
  })

  it('does not require homepage to be filled in', async () => {
    render(<CompleteMetadataForm inputDir="/data/camtrapdp" summary={partialSummary} onComplete={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('Description'), 'A test dataset.')
    await userEvent.type(screen.getByLabelText('Version'), '1.0')
    await userEvent.type(screen.getByLabelText('License ID'), 'CC-BY-4.0')
    await userEvent.type(screen.getByLabelText('License name'), 'CC BY 4.0')
    await userEvent.type(screen.getByLabelText('Author 1 name'), 'Alice')

    expect(screen.getByLabelText('Homepage (optional)')).toHaveValue('')
    expect(screen.getByRole('button', { name: /continue/i })).toBeEnabled()
  })

  it('submits only the fields that were missing, and reports the merged result', async () => {
    const onComplete = vi.fn()
    mockedApi.completeProductMetadata.mockResolvedValue({
      product_type: 'camtrapdp', title: 'My Dataset', description: 'A test dataset.', version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }], homepage: null,
    })
    render(<CompleteMetadataForm inputDir="/data/camtrapdp" summary={partialSummary} onComplete={onComplete} />)

    await userEvent.type(screen.getByLabelText('Description'), 'A test dataset.')
    await userEvent.type(screen.getByLabelText('Version'), '1.0')
    await userEvent.type(screen.getByLabelText('License ID'), 'CC-BY-4.0')
    await userEvent.type(screen.getByLabelText('License name'), 'CC BY 4.0')
    await userEvent.type(screen.getByLabelText('Author 1 name'), 'Alice')

    await userEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() => expect(mockedApi.completeProductMetadata).toHaveBeenCalled())
    expect(mockedApi.completeProductMetadata).toHaveBeenCalledWith('/data/camtrapdp', {
      description: 'A test dataset.',
      version: '1.0',
      license: { id: 'CC-BY-4.0', name: 'CC BY 4.0', url: '' },
      authors: [{ name: 'Alice', affiliation: '' }],
    })
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ title: 'My Dataset' })))
  })

  it('lets the user add and remove author rows', async () => {
    render(<CompleteMetadataForm inputDir="/data/camtrapdp" summary={partialSummary} onComplete={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /add author/i }))
    expect(screen.getByLabelText('Author 2 name')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /remove author 2/i }))
    expect(screen.queryByLabelText('Author 2 name')).not.toBeInTheDocument()
  })
})
