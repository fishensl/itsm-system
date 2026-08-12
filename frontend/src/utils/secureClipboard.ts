/**
 * Copy a sensitive value and clear it after ten seconds when clipboard access
 * confirms that the user has not copied something else in the meantime.
 */
export async function copySensitiveText(value: string, clearAfterMs = 10_000): Promise<void> {
  await navigator.clipboard.writeText(value)
  window.setTimeout(async () => {
    try {
      const current = await navigator.clipboard.readText()
      if (current === value) await navigator.clipboard.writeText('')
    } catch {
      // Browsers may deny clipboard read permission; never overwrite blindly.
    }
  }, clearAfterMs)
}
