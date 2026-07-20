import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import HFHPublishForm from './HFHPublishForm'

vi.mock('../api', () => ({
  api: {
    hfhGetConfig: vi.fn(),
    hfhTestToken: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.hfhGetConfig.mockResolvedValue({
    username: null, output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: false,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

// Renders the form and waits for settings.toml's config to have been
// applied to its state (onOutputDirChange fires once form.outputDir is set
// from it) — a reliable flush point regardless of what else the config
// prefills (username may or may not be present).
async function renderAndWaitForConfig(onConfigured = vi.fn()) {
  const onOutputDirChange = vi.fn()
  render(<HFHPublishForm onOutputDirChange={onOutputDirChange} onConfigured={onConfigured} />)
  await waitFor(() => expect(onOutputDirChange).toHaveBeenCalledWith('/hfh/output'))
}

async function fillRepo(user: string, name: string) {
  await userEvent.type(screen.getByLabelText('User or organization'), user)
  await userEvent.type(screen.getByLabelText('Repository name'), name)
}

describe('HFHPublishForm', () => {
  it('prefills the output directory from settings', async () => {
    await renderAndWaitForConfig()
  })

  it('disables Test token and Continue until both repository fields are given', async () => {
    await renderAndWaitForConfig()

    expect(screen.getByRole('button', { name: /test token/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled()

    await userEvent.type(screen.getByLabelText('User or organization'), 'alice')
    expect(screen.getByRole('button', { name: /test token/i })).toBeDisabled()
  })

  it('shows the combined repository identifier once both fields are filled', async () => {
    await renderAndWaitForConfig()

    expect(screen.queryByText('alice/dataset')).not.toBeInTheDocument()

    await fillRepo('alice', 'dataset')

    const identifier = screen.getByText('alice/dataset')
    expect(identifier).toBeInTheDocument()
    expect(identifier.parentElement?.textContent).toContain('The repository identifier will be:')
  })

  it('tests the token and shows the connected username', async () => {
    mockedApi.hfhTestToken.mockResolvedValue({ ok: true, username: 'alice', version_conflict: false })
    await renderAndWaitForConfig()

    await fillRepo('alice', 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('button', { name: /test token/i }))

    expect(await screen.findByText('Connected as alice.')).toBeInTheDocument()
    expect(mockedApi.hfhTestToken).toHaveBeenCalledWith('alice/dataset', 'hf_x', undefined)
  })

  it('warns when the version has already been published to this repository', async () => {
    mockedApi.hfhTestToken.mockResolvedValue({ ok: true, username: 'alice', version_conflict: true })
    render(<HFHPublishForm productVersion="1.0" onOutputDirChange={vi.fn()} onConfigured={vi.fn()} />)
    await waitFor(() => expect(mockedApi.hfhGetConfig).toHaveBeenCalled())

    await fillRepo('alice', 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('button', { name: /test token/i }))

    expect(await screen.findByText(/already been published/i)).toBeInTheDocument()
    expect(mockedApi.hfhTestToken).toHaveBeenCalledWith('alice/dataset', 'hf_x', '1.0')
    // still just a warning — Continue isn't blocked by it (the real enforcement is server-side, at publish time)
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
  })

  it('shows an error message when the token is rejected', async () => {
    mockedApi.hfhTestToken.mockRejectedValue(new Error('Incorrect or expired HuggingFace Hub token.'))
    await renderAndWaitForConfig()

    await fillRepo('alice', 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_bad')
    await userEvent.click(screen.getByRole('button', { name: /test token/i }))

    expect(await screen.findByText('Incorrect or expired HuggingFace Hub token.')).toBeInTheDocument()
  })

  it('enables Test token and Continue with a blank token when one is already saved', async () => {
    mockedApi.hfhGetConfig.mockResolvedValue({
      username: 'alice', output_dir: '/hfh/output', version: '1.0', timeout: 60, has_token: true,
    })
    render(<HFHPublishForm productTitle="Dataset" onConfigured={vi.fn()} />)

    await waitFor(() => expect(screen.getByLabelText('User or organization')).toHaveValue('alice'))
    await waitFor(() => expect(screen.getByLabelText('Repository name')).toHaveValue('dataset'))

    expect(screen.getByRole('button', { name: /test token/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeEnabled()
    expect(screen.getByText('Already saved — leave blank to reuse it.')).toBeInTheDocument()
  })

  it('prefills the repository name from the product title, lowercased and without spaces', async () => {
    render(<HFHPublishForm productTitle="My Camtrap DP Dataset" onConfigured={vi.fn()} />)

    await waitFor(() => expect(screen.getByLabelText('Repository name')).toHaveValue('mycamtrapdpdataset'))
  })

  it('does not overwrite a repository name the user already typed, even if the product title changes later', async () => {
    const { rerender } = render(<HFHPublishForm productTitle="First Title" onConfigured={vi.fn()} />)
    await waitFor(() => expect(screen.getByLabelText('Repository name')).toHaveValue('firsttitle'))

    await userEvent.clear(screen.getByLabelText('Repository name'))
    await userEvent.type(screen.getByLabelText('Repository name'), 'custom-name')

    rerender(<HFHPublishForm productTitle="A Different Title" onConfigured={vi.fn()} />)

    expect(screen.getByLabelText('Repository name')).toHaveValue('custom-name')
  })

  it('defaults to mirror mode', async () => {
    await renderAndWaitForConfig()

    expect(screen.getByRole('radio', { name: /mirror/i })).toBeChecked()

    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))

    expect(screen.getByRole('radio', { name: /^link/i })).toBeChecked()
  })

  it('reports the collected configuration when Continue is clicked', async () => {
    const onConfigured = vi.fn()
    await renderAndWaitForConfig(onConfigured)

    await fillRepo('alice', 'dataset')
    await userEvent.type(screen.getByLabelText('HuggingFace Hub token'), 'hf_x')
    await userEvent.click(screen.getByRole('radio', { name: /^link/i }))
    await userEvent.click(screen.getByRole('radio', { name: /same as input/i }))

    await userEvent.click(screen.getByRole('button', { name: /^continue$/i }))

    expect(onConfigured).toHaveBeenCalledWith({
      repoId: 'alice/dataset', token: 'hf_x', priv: true, mirrorImages: false,
      outputMode: 'passthrough', outputDir: '/hfh/output',
    })
  })
})
