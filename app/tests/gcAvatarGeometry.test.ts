import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const avatarSource = readFileSync(new URL('../src/components/GcAvatar.vue', import.meta.url), 'utf8')

describe('GcAvatar geometry baseline', () => {
  it('uses a centered aspectFill image clipped by a fixed square frame', () => {
    expect(avatarSource).toContain('mode="aspectFill"')
    expect(avatarSource).toContain('aspect-ratio: 1 / 1')
    expect(avatarSource).toContain('box-sizing: border-box')
    expect(avatarSource).toContain('overflow: hidden')
    expect(avatarSource).toContain('border-radius: 50%')
    expect(avatarSource).toContain('position: absolute')
    expect(avatarSource).toContain('inset: 0')
    expect(avatarSource).toContain('object-position: center')
  })

  it('keeps header and profile frames at their frozen dimensions', () => {
    expect(avatarSource).toMatch(/\.gc-avatar--header\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;/s)
    expect(avatarSource).toMatch(/\.gc-avatar--profile\s*\{[^}]*width:\s*76px;[^}]*height:\s*76px;/s)
    expect(avatarSource).toMatch(/\.gc-avatar--profile::after\s*\{[^}]*inset:\s*0;[^}]*border:\s*5px solid #fff;/s)
    expect(avatarSource).toMatch(/\.gc-avatar__image\s*\{[^}]*width:\s*100%;[^}]*height:\s*100%;/s)
  })
})
