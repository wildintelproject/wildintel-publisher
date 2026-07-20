import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import DirectoryPicker from './DirectoryPicker'

vi.mock('../api', () => ({
  api: { fsBrowse: vi.fn() },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.fsBrowse.mockResolvedValue({
    current: '/home/user',
    parent: '/home',
    dirs: [{ name: 'camtrapdp', path: '/home/user/camtrapdp' }],
  })
})

describe('DirectoryPicker', () => {
  it('browses the initial path on mount and lists its subdirectories', async () => {
    render(<DirectoryPicker onSelect={vi.fn()} onClose={vi.fn()} initialPath="/home/user" />)

    expect(await screen.findByRole('button', { name: /camtrapdp/i })).toBeInTheDocument()
    expect(mockedApi.fsBrowse).toHaveBeenCalledWith('/home/user')
  })

  it('navigates into a subdirectory on double-click', async () => {
    render(<DirectoryPicker onSelect={vi.fn()} onClose={vi.fn()} initialPath="/home/user" />)
    await screen.findByRole('button', { name: /camtrapdp/i })

    mockedApi.fsBrowse.mockResolvedValueOnce({ current: '/home/user/camtrapdp', parent: '/home/user', dirs: [] })
    await userEvent.dblClick(screen.getByRole('button', { name: /camtrapdp/i }))

    await waitFor(() => expect(mockedApi.fsBrowse).toHaveBeenCalledWith('/home/user/camtrapdp'))
  })

  it('calls onSelect with the manual path and closes when Select is clicked', async () => {
    const onSelect = vi.fn()
    const onClose = vi.fn()
    render(<DirectoryPicker onSelect={onSelect} onClose={onClose} initialPath="/home/user" />)
    await screen.findByRole('button', { name: /camtrapdp/i })

    await userEvent.click(screen.getByRole('button', { name: /^select$/i }))

    expect(onSelect).toHaveBeenCalledWith('/home/user')
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn()
    render(<DirectoryPicker onSelect={vi.fn()} onClose={onClose} initialPath="/home/user" />)
    await screen.findByRole('button', { name: /camtrapdp/i })

    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onClose).toHaveBeenCalled()
  })
})
