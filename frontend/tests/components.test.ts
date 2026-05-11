import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Badge from '../src/components/shared/Badge.vue'
import ProgressBar from '../src/components/shared/ProgressBar.vue'
import Card from '../src/components/shared/Card.vue'
import EmptyState from '../src/components/shared/EmptyState.vue'

describe('Shared Components', () => {
  it('Badge rendert mit Variant', () => {
    const w = mount(Badge, { props: { variant: 'green', dot: true }, slots: { default: 'Online' } })
    expect(w.text()).toContain('Online')
    expect(w.html()).toContain('bg-green-')
  })

  it('ProgressBar rechnet Prozent', () => {
    const w = mount(ProgressBar, { props: { value: 50, max: 100, label: 'Test' } })
    expect(w.text()).toContain('Test')
    expect(w.text()).toContain('50%')
  })

  it('ProgressBar wird rot bei >= 90 %', () => {
    const w = mount(ProgressBar, { props: { value: 95, max: 100 } })
    expect(w.html()).toContain('bg-red-500')
  })

  it('Card rendert Title und Slot', () => {
    const w = mount(Card, {
      props: { title: 'Mein Card' },
      slots: { default: '<p>Inhalt</p>' },
    })
    expect(w.text()).toContain('Mein Card')
    expect(w.text()).toContain('Inhalt')
  })

  it('EmptyState rendert Default-Text', () => {
    const w = mount(EmptyState, { props: { title: 'Leer', message: 'Nix da.' } })
    expect(w.text()).toContain('Leer')
    expect(w.text()).toContain('Nix da.')
  })
})
