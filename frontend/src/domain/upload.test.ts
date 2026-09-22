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

  it('accepts a file at exactly the ceiling', () => {
    expect(validateFile(fileOfSize('sales.csv', UPLOAD_CEILING_BYTES))).toBeNull()
  })
})
