import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { api } from '../api'
import TrapperConnectionForm from './TrapperConnectionForm'

vi.mock('../api', () => ({
  api: {
    trapperGetConfig: vi.fn(),
    trapperTestConnection: vi.fn(),
    trapperResearchProjects: vi.fn(),
    trapperClassificationProjects: vi.fn(),
    trapperDeployments: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.trapperGetConfig.mockResolvedValue({ base_url: null, user_name: null, has_password: false })
})

function renderForm(onSelectionChange = vi.fn()) {
  render(<TrapperConnectionForm onSelectionChange={onSelectionChange} />)
  return onSelectionChange
}

async function fillCredentials() {
  await userEvent.type(screen.getByPlaceholderText('https://trapper.example.com'), 'https://trapper.example')
  await userEvent.type(screen.getByLabelText('Username'), 'alice')
  await userEvent.type(screen.getByLabelText('Password'), 'secret')
}

async function selectDeployment() {
  mockedApi.trapperTestConnection.mockResolvedValue({ ok: true, research_projects_count: 1 })
  mockedApi.trapperResearchProjects.mockResolvedValue({ results: [{ pk: 1, name: 'Project A', acronym: 'PA' }] })
  mockedApi.trapperClassificationProjects.mockResolvedValue({ results: [{ pk: 10, name: 'Classif A', is_active: true }] })
  mockedApi.trapperDeployments.mockResolvedValue({
    results: [{ pk: 100, deployment_id: 'r0007-dona_0018', location_id: 'L1' }],
  })

  await fillCredentials()
  await userEvent.click(screen.getByRole('button', { name: /test connection/i }))
  await waitFor(() => expect(screen.getByLabelText('Research project')).toBeInTheDocument())
  await userEvent.selectOptions(screen.getByLabelText('Research project'), '1')
  await waitFor(() => expect(screen.getByLabelText('Classification project')).toBeEnabled())
  await userEvent.selectOptions(screen.getByLabelText('Classification project'), '10')
  await waitFor(() => expect(screen.getByLabelText('Deployment')).toBeEnabled())
  await userEvent.selectOptions(screen.getByLabelText('Deployment'), '100')
}

describe('TrapperConnectionForm', () => {
  it('disables Test Connection until all three fields are filled', async () => {
    renderForm()

    expect(screen.getByRole('button', { name: /test connection/i })).toBeDisabled()

    await fillCredentials()

    expect(screen.getByRole('button', { name: /test connection/i })).toBeEnabled()
  })

  it('shows an error message when the connection fails', async () => {
    mockedApi.trapperTestConnection.mockRejectedValue(new Error('Incorrect Trapper username or password.'))

    renderForm()
    await fillCredentials()
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))

    expect(await screen.findByText('Incorrect Trapper username or password.')).toBeInTheDocument()
  })

  it('walks through research project -> classification project -> deployment on success', async () => {
    renderForm()
    await selectDeployment()

    expect(screen.getByText('r0007-dona_0018')).toBeInTheDocument()
  })

  it('resets downstream selections when a credential field changes', async () => {
    mockedApi.trapperTestConnection.mockResolvedValue({ ok: true, research_projects_count: 1 })
    mockedApi.trapperResearchProjects.mockResolvedValue({ results: [{ pk: 1, name: 'Project A', acronym: 'PA' }] })

    renderForm()
    await fillCredentials()
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))
    await waitFor(() => expect(screen.getByLabelText('Research project')).toBeInTheDocument())

    await userEvent.type(screen.getByLabelText('Username'), 'x')

    expect(screen.queryByLabelText('Research project')).not.toBeInTheDocument()
  })

  it('prefills url and username from the saved configuration', async () => {
    mockedApi.trapperGetConfig.mockResolvedValue({
      base_url: 'https://trapper.example', user_name: 'alice', has_password: true,
    })

    renderForm()

    await waitFor(() => expect(screen.getByLabelText('Trapper URL')).toHaveValue('https://trapper.example'))
    expect(screen.getByLabelText('Username')).toHaveValue('alice')
    expect(screen.getByLabelText('Password')).toHaveValue('')
    expect(screen.getByText('Already saved — leave blank to reuse it.')).toBeInTheDocument()
  })

  it('enables Test Connection with a blank password when one is already saved', async () => {
    mockedApi.trapperGetConfig.mockResolvedValue({
      base_url: 'https://trapper.example', user_name: 'alice', has_password: true,
    })

    renderForm()
    await waitFor(() => expect(screen.getByLabelText('Trapper URL')).toHaveValue('https://trapper.example'))

    expect(screen.getByRole('button', { name: /test connection/i })).toBeEnabled()
  })

  it('calls test-connection with a blank password to reuse the saved one', async () => {
    mockedApi.trapperGetConfig.mockResolvedValue({
      base_url: 'https://trapper.example', user_name: 'alice', has_password: true,
    })
    mockedApi.trapperTestConnection.mockResolvedValue({ ok: true, research_projects_count: 1 })
    mockedApi.trapperResearchProjects.mockResolvedValue({ results: [] })

    renderForm()
    await waitFor(() => expect(screen.getByLabelText('Trapper URL')).toHaveValue('https://trapper.example'))

    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))

    await waitFor(() => expect(mockedApi.trapperTestConnection).toHaveBeenCalledWith('https://trapper.example', 'alice', ''))
  })

  it('reports the selection once a deployment is chosen, with events included by default', async () => {
    const onSelectionChange = renderForm()
    await selectDeployment()

    await waitFor(() => expect(onSelectionChange).toHaveBeenCalledWith({
      url: 'https://trapper.example', username: 'alice', password: 'secret',
      projectId: 10, deploymentId: 'r0007-dona_0018', includeEvents: true,
    }))
  })

  it('reports includeEvents=false once the checkbox is unchecked', async () => {
    const onSelectionChange = renderForm()
    await selectDeployment()
    await waitFor(() => expect(onSelectionChange).toHaveBeenCalledWith(expect.objectContaining({ includeEvents: true })))

    await userEvent.click(screen.getByRole('checkbox', { name: /include events/i }))

    await waitFor(() => expect(onSelectionChange).toHaveBeenLastCalledWith(expect.objectContaining({ includeEvents: false })))
  })

  it('clears the selection when an upstream field changes after a deployment was chosen', async () => {
    const onSelectionChange = renderForm()
    await selectDeployment()
    await waitFor(() => expect(onSelectionChange).toHaveBeenCalledWith(expect.objectContaining({ deploymentId: 'r0007-dona_0018' })))

    await userEvent.type(screen.getByLabelText('Username'), 'x')

    expect(onSelectionChange).toHaveBeenLastCalledWith(null)
  })
})
