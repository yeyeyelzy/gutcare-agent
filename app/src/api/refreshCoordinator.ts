export class RefreshCoordinator<T> {
  private active: Promise<T> | null = null

  run(refresh: () => Promise<T>): Promise<T> {
    if (this.active) return this.active
    const operation = refresh()
    this.active = operation
    void operation.finally(() => {
      if (this.active === operation) this.active = null
    }).catch(() => undefined)
    return operation
  }
}
