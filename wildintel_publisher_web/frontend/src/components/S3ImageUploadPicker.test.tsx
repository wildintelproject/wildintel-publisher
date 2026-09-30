import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import S3ImageUploadPicker, { EMPTY_S3_CONFIG } from './S3ImageUploadPicker'
import type { S3Config } from './S3ImageUploadPicker'

vi.mock('../api', () => ({ api: { s3GetConfig: vi.fn(), s3TestConnection: vi.fn() } }))
const mockedApi = vi.mocked(api)

function Harness() {
  const [config, setConfig] = useState<S3Config>(EMPTY_S3_CONFIG)
  return <S3ImageUploadPicker wanted={true} onWantedChange={() => {}} config={config} onConfigChange={setConfig} />
}

beforeEach(() => {
  vi.resetAllMocks()
  mockedApi.s3GetConfig.mockResolvedValue({
    endpoint_url: 'https://s3.example.org', region: 'garage', bucket: 'public', prefix: null, public_base_url: null,
    verify_ssl: true, has_access_key: false, has_secret_key: false,
  })
  mockedApi.s3TestConnection.mockResolvedValue({ ok: true })
})

describe('S3ImageUploadPicker', () => {
  it('sends verifySsl false to Test connection once "Don\'t validate the SSL certificate" is ticked', async () => {
    render(<Harness />)
    await waitFor(() => expect(screen.getByLabelText('Bucket')).toHaveValue('public'))
    await userEvent.click(screen.getByRole('checkbox', { name: /don't validate the ssl certificate/i }))
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))
    await waitFor(() => expect(mockedApi.s3TestConnection).toHaveBeenCalledWith(
      expect.objectContaining({ verifySsl: false }),
    ))
  })

  it('validates the certificate by default', async () => {
    render(<Harness />)
    await waitFor(() => expect(screen.getByLabelText('Bucket')).toHaveValue('public'))
    await userEvent.click(screen.getByRole('button', { name: /test connection/i }))
    await waitFor(() => expect(mockedApi.s3TestConnection).toHaveBeenCalledWith(
      expect.objectContaining({ verifySsl: true }),
    ))
  })
})
