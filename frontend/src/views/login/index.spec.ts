import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'


describe('login form native submission safety', () => {
  it('prevents Edge implicit form navigation for password and MFA Enter', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/login/index.vue'), 'utf8')

    expect(source.match(/@submit\.prevent="submit"/g)).toHaveLength(1)
    expect(source.match(/@submit\.prevent="submitMfa"/g)).toHaveLength(1)
    expect(source.match(/native-type="submit"/g)).toHaveLength(2)
    expect(source).not.toContain('@keyup.enter')
  })
})
