import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { existsSync, readdirSync, mkdirSync, mkdtempSync, readFileSync, rmdirSync, unlinkSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import YAML from 'yaml'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = resolve(appRoot, '..')
const contractPath = join(repoRoot, 'contracts/openapi/gutcare-v1.yaml')
const generatedPath = join(appRoot, 'src/api/generated/openapi.ts')
const requestedMode = process.argv[2]

if (requestedMode !== '--write' && requestedMode !== '--check') {
  throw new Error('Use --write to regenerate or --check to verify generated OpenAPI types.')
}

const document = YAML.parse(readFileSync(contractPath, 'utf8'))
const requiredOperationIds = new Set([
  'register',
  'verifyEmail',
  'login',
  'refreshSession',
  'logout',
  'requestPasswordReset',
  'confirmPasswordReset',
  'getMyProfile',
  'updateMyProfile',
  'listRecords',
  'createRecord',
  'getRecord',
  'updateRecord',
  'deleteRecord',
  'listActivityRecords',
  'createActivityRecord',
  'getActivityRecord',
  'patchActivityRecord',
  'deleteActivityRecord',
  'getHistoryTimeline',
  'getTrends',
  'previewAnalysisTask',
  'createAnalysisTask',
  'listAnalysisTasks',
  'getAnalysisTask',
  'cancelAnalysisTask',
  'retryAnalysisTask',
  'listAdvice',
  'getAdvice',
  'readAdvice',
  'archiveAdvice',
  'updateAdviceFeedback',
  'getSymptomStatusHistory',
  'listMoodRecords',
  'createMoodRecord',
  'getMoodRecord',
  'patchMoodRecord',
  'deleteMoodRecord',
  'listMedicationPlans',
  'createMedicationPlan',
  'getMedicationPlan',
  'updateMedicationPlan',
  'deleteMedicationPlan',
  'transitionMedicationPlan',
  'listMedicationSchedules',
  'createMedicationSchedule',
  'updateMedicationSchedule',
  'deleteMedicationSchedule',
  'listMedicationCheckins',
  'listTodayMedicationCheckins',
  'updateMedicationCheckin',
  'getMyConsents',
  'getConsentNotice',
  'recordConsent',
  'listRiskAlerts',
  'getRiskAlert',
  'markRiskAlertRead',
  'reevaluateRiskAlert',
  'listNotifications',
  'getNotificationUnreadCount',
  'getNotificationPreferences',
  'updateNotificationPreferences',
  'readNotificationBatch',
  'getNotification',
  'readNotification',
  'requestAccountDeletion',
  'getPrivacyDeletionStatus',
  'createPrivacyExport',
  'listPrivacyExports',
  'getPrivacyExport',
  'confirmPrivacyExport',
  'cancelPrivacyExport',
  'downloadPrivacyExport',
  'createUpload',
  'completeUpload',
  'uploadThroughGateway',
  'downloadThroughGateway',
  'listMedicalDocuments',
  'createMedicalDocument',
  'getMedicalDocument',
  'updateMedicalDocument',
  'deleteMedicalDocument',
  'createFileDownloadGrant',
])
const httpMethods = new Set(['get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'])
const foundOperations = new Map()

for (const [path, pathItem] of Object.entries(document.paths ?? {})) {
  for (const [method, operation] of Object.entries(pathItem ?? {})) {
    if (!httpMethods.has(method) || typeof operation !== 'object' || operation === null) continue
    const operationId = operation.operationId
    if (typeof operationId !== 'string' || !requiredOperationIds.has(operationId)) continue
    const locations = foundOperations.get(operationId) ?? []
    locations.push({ path, method })
    foundOperations.set(operationId, locations)
  }
}

const missingOperations = [...requiredOperationIds].filter((operationId) => !foundOperations.has(operationId))
const duplicatedOperations = [...foundOperations.entries()].filter(([, locations]) => locations.length !== 1)
if (missingOperations.length || duplicatedOperations.length || foundOperations.size !== requiredOperationIds.size) {
  throw new Error(`APP OpenAPI operation set mismatch. Missing: ${missingOperations.join(', ') || 'none'}; duplicated: ${duplicatedOperations.map(([id]) => id).join(', ') || 'none'}.`)
}

// Generate frozen auth/profile/F13, F02 files/medical documents, F03-F08/F10-F12/F14 and F06 medication surfaces. Every DTO
// remains derived from the authoritative OpenAPI contract.
const subset = {
  ...document,
  paths: Object.fromEntries([...new Set([...foundOperations.values()].flat().map(({ path }) => path))].map((path) => {
    const original = document.paths[path]
    const filtered = Object.fromEntries(Object.entries(original).filter(([key, value]) =>
      !httpMethods.has(key) || (typeof value === 'object' && value !== null && requiredOperationIds.has(value.operationId)),
    ))
    return [path, filtered]
  })),
}

const scratchPrefix = '.tmp-openapi-generation-'
const normalizeEol = (value) => value.replace(/\r\n?/g, '\n')
const temporaryDirectory = mkdtempSync(join(appRoot, scratchPrefix))
try {
  const temporaryContract = join(temporaryDirectory, 'app-surface.yaml')
  const temporaryOutput = join(temporaryDirectory, 'openapi.ts')
  writeFileSync(temporaryContract, YAML.stringify(subset), 'utf8')

  const require = createRequire(import.meta.url)
  const packageEntry = require.resolve('openapi-typescript')
  const cliPath = resolve(dirname(packageEntry), '../bin/cli.js')
  const result = spawnSync(process.execPath, [
    cliPath,
    relative(appRoot, temporaryContract),
    '-o',
    relative(appRoot, temporaryOutput),
  ], {
    cwd: appRoot,
    encoding: 'utf8',
  })
  if (result.stdout) process.stdout.write(result.stdout)
  if (result.stderr) process.stderr.write(result.stderr)
  if (result.status !== 0) throw new Error(`openapi-typescript failed with exit code ${result.status ?? 'unknown'}.`)

  const generated = normalizeEol(readFileSync(temporaryOutput, 'utf8'))
  if (requestedMode === '--write') {
    mkdirSync(dirname(generatedPath), { recursive: true })
    writeFileSync(generatedPath, generated, 'utf8')
    process.stdout.write(`Generated ${generatedPath}\n`)
  } else {
    const checkedInBytes = readFileSync(generatedPath)
    if (checkedInBytes[0] === 0xef && checkedInBytes[1] === 0xbb && checkedInBytes[2] === 0xbf) {
      throw new Error('Generated OpenAPI types must be UTF-8 without a BOM.')
    }
    const checkedIn = checkedInBytes.toString('utf8')
    if (checkedIn.includes('\r')) {
      throw new Error('Generated OpenAPI types must use LF line endings. Ensure Git checks out this file with LF.')
    }
    if (generated !== checkedIn) {
      throw new Error('Generated OpenAPI types differ. Run `pnpm openapi:generate` and review the result.')
    }
    process.stdout.write('Generated OpenAPI auth/profile/privacy/F02/F03–F08/F10–F12/F14 types are current.\n')
  }
} finally {
  // The CLI is launched synchronously above, so no process retains these files.
  // Delete exact files first, then remove the now-empty unique directory; this is
  // reliable on Windows where recursive cleanup may leave an open-handle residue.
  for (const filename of ['app-surface.yaml', 'openapi.ts']) {
    const temporaryFile = join(temporaryDirectory, filename)
    if (existsSync(temporaryFile)) unlinkSync(temporaryFile)
  }
  if (existsSync(temporaryDirectory)) rmdirSync(temporaryDirectory)
}

const workspaceScratch = readdirSync(appRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && entry.name.startsWith(scratchPrefix))
  .map((entry) => entry.name)
if (workspaceScratch.length) {
  throw new Error(`OpenAPI generation left workspace scratch directories: ${workspaceScratch.join(', ')}.`)
}
