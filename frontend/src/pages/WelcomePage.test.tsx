import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WelcomePage from './WelcomePage'
import { api } from '../api'

vi.mock('../api', () => ({ api: { setShowWelcome: vi.fn() } }))
const mockedApi = vi.mocked(api, true)

describe('WelcomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.setShowWelcome.mockResolvedValue({ show_welcome: false })
  })

  it('shows the brand title and the steps of the wizard in order', () => {
    render(<WelcomePage onStart={() => {}} />)

    expect(screen.getByText('WildINTEL Publisher')).toBeInTheDocument()
    const steps = screen.getAllByRole('listitem').map((li) => li.querySelector('strong')?.textContent)
    expect(steps).toEqual(['Choose', 'Fetch', 'Review', 'Package', 'Publish'])
    expect(screen.getByText(/B2SHARE, GBIF, Hugging Face Hub or Zenodo/)).toBeInTheDocument()
  })

  it('calls onStart when the Get Started button is clicked', async () => {
    const onStart = vi.fn()
    render(<WelcomePage onStart={onStart} />)

    await userEvent.click(screen.getByRole('button', { name: /get started/i }))

    expect(onStart).toHaveBeenCalledOnce()
  })

  it('saves that the page is not shown again when its tick is ticked', async () => {
    render(<WelcomePage onStart={() => {}} />)

    await userEvent.click(screen.getByRole('checkbox', { name: /do not show this page again/i }))

    expect(mockedApi.setShowWelcome).toHaveBeenCalledWith(false)
    expect(screen.getByRole('checkbox', { name: /do not show this page again/i })).toBeChecked()
  })

  it('unticks and says so when the setting could not be saved', async () => {
    mockedApi.setShowWelcome.mockRejectedValue(new Error('disk full'))
    render(<WelcomePage onStart={() => {}} />)

    await userEvent.click(screen.getByRole('checkbox', { name: /do not show this page again/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('disk full'))
    expect(screen.getByRole('checkbox', { name: /do not show this page again/i })).not.toBeChecked()
  })
})
