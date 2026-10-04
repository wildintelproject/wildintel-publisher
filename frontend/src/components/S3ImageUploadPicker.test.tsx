import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import S3ImageUploadPicker, { EMPTY_S3_CONFIG } from './S3ImageUploadPicker'
import type { S3Config } from './S3ImageUploadPicker'
import type { S3Remote } from '../types'

vi.mock('../api', () => ({ api: { s3GetConfig: vi.fn(), s3TestConnection: vi.fn() } }))
const mockedApi = vi.mocked(api)

const remote = (id: string, name: string, bucket: string): S3Remote => ({
  id, name, endpoint_url: 'https://s3.example.org', region: 'garage', bucket, prefix: null, public_base_url: null,
  verify_ssl: true, has_access_key: true, has_secret_key: true,
})

let lastConfig: S3Config = EMPTY_S3_CONFIG

function Harness() {
  const [config, setConfig] = useState<S3Config>(EMPTY_S3_CONFIG)
  lastConfig = config
  return <S3ImageUploadPicker wanted={true} onWantedChange={() => {}} config={config} onConfigChange={setConfig} />
}

beforeEach(() => {
  vi.resetAllMocks()
  mockedApi.s3TestConnection.mockResolvedValue({ ok: true })
})

describe('S3ImageUploadPicker', () => {
  it('pre-selects the only saved remote', async () => {
    mockedApi.s3GetConfig.mockResolvedValue({ remotes: [remote('r1', 'WildINTEL', 'public')] })
    render(<Harness />)
    await waitFor(() => expect(screen.getByLabelText('Remote')).toHaveValue('r1'))
    expect(lastConfig.remoteId).toBe('r1')
  })

  it('makes the user choose among several remotes, and tests the chosen one', async () => {
    mockedApi.s3GetConfig.mockResolvedValue({ remotes: [remote('r1', 'WildINTEL', 'public'), remote('r2', 'Backup', 'backup')] })
    render(<Harness />)
    await waitFor(() => expect(screen.getByLabelText('Remote')).toHaveValue(''))
    expect(screen.getByRole('button', { name: /test connection/i })).toBeDisabled()

    await userEvent.selectOptions(screen.getByLabelText('Remote'), 'r2')
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))
    await waitFor(() => expect(mockedApi.s3TestConnection).toHaveBeenCalledWith({ remoteId: 'r2' }))
    expect(await screen.findByText(/connection successful/i)).toBeInTheDocument()
  })

  it('points to the settings page when no remote is saved', async () => {
    mockedApi.s3GetConfig.mockResolvedValue({ remotes: [] })
    render(<Harness />)
    expect(await screen.findByText(/no s3 remote saved yet/i)).toBeInTheDocument()
  })
})
