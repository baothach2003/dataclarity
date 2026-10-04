import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/errors.ts'
import { UPLOAD_CEILING_BYTES, validateFile } from './upload.ts'

function fileOfSize(name: string, size: number): File {
  const file = new File([new Uint8Array(1)], name, { type: 'text/csv' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('validateFile', () => {
  it('accepts a .csv file within the size ceiling', () => {
    expect(validateFile(fileOfSize('sales.csv', 1024))).toBeNull()
  })

  it('accepts .CSV case-insensitively (SEC-1)', () => {
    expect(validateFile(fileOfSize('sales.CSV', 1024))).toBeNull()
  })

  it('rejects a non-.csv extension as UNSUPPORTED_TYPE', () => {
    const error = validateFile(fileOfSize('sales.xlsx', 1024))

    expect(error).toBeInstanceOf(ApiError)
    expect(error?.code).toBe('UNSUPPORTED_TYPE')
  })

  it('rejects a file over the 50MB ceiling as FILE_TOO_LARGE', () => {
    const error = validateFile(fileOfSize('sales.csv', UPLOAD_CEILING_BYTES + 1))

    expect(error?.code).toBe('FILE_TOO_LARGE')
  })

  it("marks a refusal at the ceiling as not the server's limit while that is unknown (6A-6D review B3)", () => {
    const error = validateFile(fileOfSize('sales.csv', UPLOAD_CEILING_BYTES + 1), null)

    expect(error?.details).toEqual({ max_bytes: UPLOAD_CEILING_BYTES, limit_known: false })
  })

  it('accepts a file at exactly the ceiling', () => {
    expect(validateFile(fileOfSize('sales.csv', UPLOAD_CEILING_BYTES))).toBeNull()
  })

  it("rejects at the server's own lower limit when it is known (6A)", () => {
    const tenMb = 10 * 1024 * 1024

    expect(validateFile(fileOfSize('sales.csv', tenMb), 10)).toBeNull()
    const error = validateFile(fileOfSize('sales.csv', tenMb + 1), 10)
    expect(error?.code).toBe('FILE_TOO_LARGE')
    expect(error?.message).toBe('The file is larger than the 10 MB limit.')
    expect(error?.details).toEqual({ max_bytes: tenMb })
  })

  it('never lets a limit above the SPECS ceiling raise it (SEC-1)', () => {
    expect(validateFile(fileOfSize('sales.csv', UPLOAD_CEILING_BYTES + 1), 80)?.code).toBe(
      'FILE_TOO_LARGE',
    )
  })
})
