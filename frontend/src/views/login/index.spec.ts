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

  it('routes an unbound first-login account to the mandatory MFA setup page', () => {
    const loginSource = readFileSync(resolve(process.cwd(), 'src/views/login/index.vue'), 'utf8')
    const setupSource = readFileSync(resolve(process.cwd(), 'src/views/mfaSetup.vue'), 'utf8')

    expect(loginSource).toContain("if (result.bind_required)")
    expect(loginSource).toContain("await router.push('/mfa')")
    expect(setupSource).toContain('首次登录必须先绑定账号 MFA')
    expect(setupSource).toContain('绑定成功后，系统会继续引导你修改初始密码')
  })

  it('keeps MFA binding visible and manually reachable for every signed-in account', () => {
    const layoutSource = readFileSync(resolve(process.cwd(), 'src/layouts/MainLayout.vue'), 'utf8')
    const routerSource = readFileSync(resolve(process.cwd(), 'src/router/index.ts'), 'utf8')

    expect(layoutSource).toContain('当前账号尚未绑定 MFA')
    expect(layoutSource).toContain('<MfaSetup v-if="pwdVisible" embedded />')
    expect(layoutSource).not.toContain('<el-dropdown-item command="mfa">')
    expect(layoutSource).toContain('const openMfaSettings = () => openPwdDialog()')
    expect(routerSource).toContain("redirect: { path: '/', query: { accountSecurity: 'mfa' } }")
    expect(routerSource).toContain("path: 'security/mfa'")
  })
})
