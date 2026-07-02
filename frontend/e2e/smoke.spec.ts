import { test, expect } from '@playwright/test'

test.describe('Orbit Smoke (S20)', () => {
  test('boot → preflight → chat → code review', async ({ page }) => {
    // 1. Navigate to boot page
    await page.goto('/#/boot')

    // 2. Wait for preflight to complete and redirect to /app
    // BootScreen polls startup-probe → passed → navigates to /app
    await page.waitForURL('/#/app', { timeout: 20000 })

    // P2-3 fix: 确认不是错误 fallback——TerminalShell 必须可见
    await expect(page.locator('.terminal-shell')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('.status-bar')).toBeVisible()

    // 4. Verify chat input is ready
    const textarea = page.locator('.terminal-chat textarea')
    await expect(textarea).toBeVisible()

    // 5. Type a message and send
    await textarea.fill('hello orbit')
    await textarea.press('Enter')

    // 6. Verify the input was cleared (message was processed)
    await expect(textarea).toHaveValue('', { timeout: 3000 })

    // 7. Test file tree — click on a file to open code review
    // FileTreePanel renders FileTreeNode components
    const fileNode = page.locator('.file-tree-panel [data-file-path]').first()
    // P2-1 fix: isVisible() 返回 Promise<boolean>，.catch() 需在 await 前
    const hasFileTree = await fileNode.isVisible({ timeout: 3000 }).catch(() => false)
    if (hasFileTree) {
      await fileNode.click()
      // Monaco panel should appear in the right panel
      await expect(page.locator('.monaco-panel')).toBeVisible({ timeout: 5000 })
    }

    // 8. Open settings via StatusBar gear
    const gearBtn = page.locator('.status-bar button[title="Settings"]')
    if (await gearBtn.isVisible()) {
      await gearBtn.click()
      await expect(page.locator('.el-dialog')).toBeVisible({ timeout: 3000 })
      // Close with Escape
      await page.keyboard.press('Escape')
    }
  })
})
