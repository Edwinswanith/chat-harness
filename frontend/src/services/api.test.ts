import { describe, expect, it } from 'vitest'
import { artifactUrl } from './api'

describe('artifactUrl', () => {
  it('keeps artifact downloads under the authenticated API path', () => {
    expect(artifactUrl('artifact-1')).toContain('/artifacts/artifact-1/download')
  })
})
