import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const component = readFileSync(new URL('../src/components/RecordImageSection.vue', import.meta.url), 'utf8')
const picker = readFileSync(new URL('../src/api/recordImagePicker.ts', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/recordImagesApi.ts', import.meta.url), 'utf8')

describe('F03/F04 record image APP', () => {
  it('keeps selection native-only, size limited, and patient CRUD independent', () => {
    expect(picker).toContain('typeof plus === \'undefined\'')
    expect(picker).toContain('MAX_IMAGE_BYTES = 10 * 1024 * 1024')
    expect(picker).toContain("sourceType: ['album', 'camera']")
    expect(component).toContain('图片为可选附件，不影响手工记录')
    expect(component).toContain("state: 'clean'")
  })

  it('requires purpose-specific acknowledgment and explicit per-field patient action', () => {
    expect(component).toContain('prepareSelection')
    expect(api).toContain('record-image-recognition-disclosures')
    expect(component).toContain('acknowledged: true')
    expect(component).toContain('确认并提交')
    expect(component).toContain("decide(candidate, 'accept')")
    expect(component).toContain("decide(candidate, 'edit')")
    expect(component).toContain("decide(candidate, 'reject')")
    expect(component).toContain('candidate_group_key')
    expect(component).toContain('candidate_dependency_unmet')
    expect(component).toContain('清除')
    expect(component).toContain('当前状态，再由你决定是否重新提交')
    expect(component).not.toMatch(/calorie|diagnosis|diagnos|bleeding|risk inference/i)
  })
})
