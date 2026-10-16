[CmdletBinding()]
param()
# Native docker/pg utilities report status through exit codes; keep stderr
# visible without allowing PowerShell to terminate before explicit checks.
$ErrorActionPreference = 'Continue'

$docker = Get-Command docker -ErrorAction Stop
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
$uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
if (-not $python -or -not $uv) { throw 'Project Python/uv resolver did not return an executable.' }
$project = $env:GUTCARE_INTEGRATION_PROJECT
if ([string]::IsNullOrWhiteSpace($project) -or $project -notmatch '^gutcare-int-[a-f0-9]{12}$') {
    throw 'Backup/restore rehearsal requires the unique integration project created by test-integration.ps1.'
}
$composeFile = 'compose.integration.yaml'
$service = 'postgres-integration'
$restoreDb = "f06_restore_$([guid]::NewGuid().ToString('N'))"
$backupPath = "/tmp/$restoreDb.dump"
$restoreBucket = "privacy-restore-$([guid]::NewGuid().ToString('N').Substring(0, 12))"

try {
    # Seed a dedicated synthetic account/patient/file rather than borrowing random
    # test residue. A pending deletion and an owned file are deliberately included.
    $privacyUserId = [guid]::NewGuid().ToString()
    $privacyPatientId = [guid]::NewGuid().ToString()
    $privacySeedSql = @'
INSERT INTO iam.user_account(id,email_ciphertext,email_lookup_hash,password_hash,status)
VALUES('__USER__',decode('01','hex'),md5('__USER__')||md5('__USER__x'),'$argon2id$restore-seed','active');
INSERT INTO health.patient_profile(id,user_id,birth_year,timezone)
VALUES('__PATIENT__','__USER__',1990,'Asia/Shanghai');
INSERT INTO health.file_object(patient_id,bucket_name,object_key,original_name,content_type,size_bytes,content_sha256,sensitivity,scan_status,storage_status)
VALUES('__PATIENT__','__BUCKET__','privacy-restore-replay/test.bin','restore-test.bin','application/octet-stream',8,repeat('a',64),'normal','clean','available');
INSERT INTO privacy.deletion_operation(account_hash,patient_id,receipt_hash,status,due_at)
VALUES(md5('__PATIENT__')||md5('__PATIENT__x'),'__PATIENT__',md5('receipt-__PATIENT__')||md5('receipt-__PATIENT__x'),'pending',now()-interval '1 hour');
'@
    $privacySeedSql = $privacySeedSql.Replace('__USER__', $privacyUserId).Replace('__PATIENT__', $privacyPatientId).Replace('__BUCKET__', $env:GUTCARE_TEST_S3_BUCKET)
    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d gutcare_business_test -v ON_ERROR_STOP=1 -c $privacySeedSql
    if ($LASTEXITCODE -ne 0) { throw 'Pending privacy deletion restore seed failed.' }

    # Keep a separate mood patient outside the deletion replay seed so the
    # restored H1 row proves the new table and sensitive JSONB survive pg_dump.
    $moodUserId = [guid]::NewGuid().ToString()
    $moodPatientId = [guid]::NewGuid().ToString()
    $moodSeedSql = @'
INSERT INTO iam.user_account(id,email_ciphertext,email_lookup_hash,password_hash,status)
VALUES('__USER__',decode('02','hex'),md5('__USER__')||md5('__USER__x'),'$argon2id$mood-restore-seed','active');
INSERT INTO health.patient_profile(id,user_id,birth_year,timezone)
VALUES('__PATIENT__','__USER__',1990,'Asia/Shanghai');
INSERT INTO health.mood_record(patient_id,occurred_at,mood_level,emotion_tags,note)
VALUES('__PATIENT__','2026-10-16T12:30:00Z',4,jsonb_build_array('calm','content'),'synthetic restore evidence');
'@
    $moodSeedSql = $moodSeedSql.Replace('__USER__', $moodUserId).Replace('__PATIENT__', $moodPatientId)
    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d gutcare_business_test -v ON_ERROR_STOP=1 -c $moodSeedSql
    if ($LASTEXITCODE -ne 0) { throw 'Mood-record restore seed failed.' }

    $env:PRIVACY_RESTORE_BUCKET = $env:GUTCARE_TEST_S3_BUCKET
    $env:PRIVACY_SOURCE_BUCKET = $env:GUTCARE_TEST_S3_BUCKET
    $env:PRIVACY_S3_ENDPOINT = $env:GUTCARE_TEST_S3_ENDPOINT
    $env:PRIVACY_S3_ACCESS_KEY = $env:GUTCARE_TEST_S3_ACCESS_KEY
    $env:PRIVACY_S3_SECRET_KEY = $env:GUTCARE_TEST_S3_SECRET_KEY
    $seedObjectVersions = @'
import os, boto3
from botocore.config import Config
c=boto3.client('s3',endpoint_url=os.environ['PRIVACY_S3_ENDPOINT'],aws_access_key_id=os.environ['PRIVACY_S3_ACCESS_KEY'],aws_secret_access_key=os.environ['PRIVACY_S3_SECRET_KEY'],config=Config(s3={'addressing_style':'path'}))
b=os.environ['PRIVACY_SOURCE_BUCKET']; c.put_bucket_versioning(Bucket=b,VersioningConfiguration={'Status':'Enabled'})
for body in (b'restore-v1',b'restore-v2'): c.put_object(Bucket=b,Key='privacy-restore-replay/test.bin',Body=body)
v=[x for x in c.list_object_versions(Bucket=b,Prefix='privacy-restore-replay/test.bin').get('Versions',[]) if x['Key']=='privacy-restore-replay/test.bin']
if len(v)<2: raise SystemExit(f'expected at least two source object versions, got {len(v)}')
'@
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        & $uv run --locked --project . --python $python python -c $seedObjectVersions
        if ($LASTEXITCODE -ne 0) { throw 'Could not seed two versioned source object versions.' }
    } finally { Pop-Location }

    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        pg_dump -U gutcare_bootstrap -Fc -d gutcare_business_test -f $backupPath
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed for the disposable PostgreSQL 18 database.' }

    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $restoreDb"
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated restore database.' }

    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        pg_restore -U gutcare_bootstrap -d $restoreDb --exit-on-error $backupPath
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed for the isolated PostgreSQL 18 restore.' }

    # Build a separate versioned restore bucket and copy every version of each key
    # recorded by the restored patient's file rows. This prevents the replay check
    # from accidentally deleting or depending on the source integration bucket.
    $env:PRIVACY_RESTORE_BUCKET = $restoreBucket
    $env:PRIVACY_SOURCE_BUCKET = $env:GUTCARE_TEST_S3_BUCKET
    $copyVersions = @'
import os, boto3
from botocore.config import Config
c=boto3.client('s3',endpoint_url=os.environ['PRIVACY_S3_ENDPOINT'],aws_access_key_id=os.environ['PRIVACY_S3_ACCESS_KEY'],aws_secret_access_key=os.environ['PRIVACY_S3_SECRET_KEY'],config=Config(s3={'addressing_style':'path'}))
dst=os.environ['PRIVACY_RESTORE_BUCKET']; src=os.environ['PRIVACY_SOURCE_BUCKET']
c.create_bucket(Bucket=dst); c.put_bucket_versioning(Bucket=dst,VersioningConfiguration={'Status':'Enabled'})
key='privacy-restore-replay/test.bin'
versions=[v for v in c.list_object_versions(Bucket=src,Prefix=key).get('Versions',[]) if v['Key']==key]
if len(versions)<2: raise SystemExit('dedicated restore replay object lacks two source versions')
for v in versions:
    c.copy_object(Bucket=dst,Key=key,CopySource={'Bucket':src,'Key':key,'VersionId':v['VersionId']})
'@
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        & $uv run --locked --project . --python $python python -c $copyVersions
        if ($LASTEXITCODE -ne 0) { throw 'Could not prepare versioned isolated MinIO restore bucket.' }
    } finally { Pop-Location }

    $restorePrivacySql = @"
UPDATE health.file_object SET bucket_name='$restoreBucket'
WHERE patient_id='$privacyPatientId';
SELECT (SELECT count(*) FROM privacy.deletion_operation WHERE account_hash=md5('$privacyPatientId')||md5('${privacyPatientId}x') AND status='pending'),
       (SELECT count(*) FROM health.file_object WHERE patient_id='$privacyPatientId');
"@
    $replaySeed = (& $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d $restoreDb -qAt -F '|' -v ON_ERROR_STOP=1 -c $restorePrivacySql) -join ''
    if ($LASTEXITCODE -ne 0 -or $replaySeed.Trim() -ne '1|1') { throw "Restored pending deletion/file seed missing: $replaySeed" }

    # The deployment pre-start gate: don't launch the API unless the one-shot replay exits cleanly.
    $env:PRIVACY_WORKER_DATABASE_URL = "postgresql+psycopg://gutcare_privacy_worker:gutcare-test-privacy-worker-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/$restoreDb"
    $env:FILES_ENDPOINT = $env:GUTCARE_TEST_S3_ENDPOINT
    $env:FILES_ACCESS_KEY = $env:GUTCARE_TEST_S3_ACCESS_KEY
    $env:FILES_SECRET_KEY = $env:GUTCARE_TEST_S3_SECRET_KEY
    $env:FILES_BUCKET = $restoreBucket
    $env:EXPORT_KEK = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        & $uv run --locked --project . --python $python python -m gutcare.privacy.worker --replay
        if ($LASTEXITCODE -ne 0) { throw 'Restored privacy replay failed; readiness must remain disabled.' }
    } finally { Pop-Location }

    $replayEvidenceSql = @"
SELECT (SELECT count(*) FROM privacy.deletion_operation WHERE account_hash=md5('$privacyPatientId')||md5('${privacyPatientId}x') AND status='completed' AND patient_id IS NULL),
       (SELECT count(*) FROM health.patient_profile WHERE id='$privacyPatientId'),
       (SELECT count(*) FROM privacy.object_inventory i JOIN privacy.deletion_operation o ON o.id=i.operation_id WHERE o.account_hash=md5('$privacyPatientId')||md5('${privacyPatientId}x') AND i.object_key IS NULL AND i.status='deleted'),
       (SELECT count(*) FROM privacy.deletion_step s JOIN privacy.deletion_operation o ON o.id=s.operation_id WHERE o.account_hash=md5('$privacyPatientId')||md5('${privacyPatientId}x') AND s.status='completed');
"@
    $replayEvidence = (& $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d $restoreDb -At -F '|' -v ON_ERROR_STOP=1 -c $replayEvidenceSql) -join ''
    $replayFields = $replayEvidence.Trim().Split('|')
    if ($LASTEXITCODE -ne 0 -or $replayFields.Count -ne 4 -or $replayFields[0] -ne '1' `
        -or $replayFields[1] -ne '0' -or [int]$replayFields[2] -lt 1 -or $replayFields[3] -ne '8') {
        throw "Restored F13 replay evidence is incomplete: $replayEvidence"
    }
    $remainingVersions = @'
import os, boto3
from botocore.config import Config
c=boto3.client('s3',endpoint_url=os.environ['PRIVACY_S3_ENDPOINT'],aws_access_key_id=os.environ['PRIVACY_S3_ACCESS_KEY'],aws_secret_access_key=os.environ['PRIVACY_S3_SECRET_KEY'],config=Config(s3={'addressing_style':'path'}))
b=os.environ['PRIVACY_RESTORE_BUCKET']; r=c.list_object_versions(Bucket=b,Prefix='privacy-restore-replay/test.bin')
print(sum(1 for v in r.get('Versions',[]) if v['Key']=='privacy-restore-replay/test.bin')+sum(1 for v in r.get('DeleteMarkers',[]) if v['Key']=='privacy-restore-replay/test.bin'))
'@
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        $versionCount = (& $uv run --locked --project . --python $python python -c $remainingVersions) -join ''
        if ($LASTEXITCODE -ne 0 -or $versionCount.Trim() -ne '0') { throw "Restored MinIO bucket retains object versions: $versionCount" }
    } finally { Pop-Location }

    $revision = (& $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d $restoreDb -At -v ON_ERROR_STOP=1 `
        -c 'SELECT version_num FROM alembic_version') -join ''
    $revisionExitCode = $LASTEXITCODE
    Push-Location (Join-Path $PSScriptRoot '..\backend')
    try {
        $expectedRevision = (& $uv run --locked --project . --python $python python -c `
            "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_current_head())") -join ''
        $expectedRevisionExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    if ($expectedRevisionExitCode -ne 0) { throw 'Could not resolve current Alembic head for restore verification.' }
    if ($revisionExitCode -ne 0 -or $revision -ne $expectedRevision.Trim()) {
        throw "Restored Alembic revision mismatch: $revision"
    }

    $evidenceSql = "SELECT (SELECT count(*) FROM health.medication_plan), " +
        "(SELECT count(*) FROM health.medication_source_ref WHERE source_deleted_at IS NOT NULL), " +
        "(SELECT count(*) FROM health.medication_idempotency), " +
        "(SELECT count(*) FROM pg_constraint WHERE conname IN " +
        "('fk_med_plan_source_ref_patient','fk_med_source_ref_live_document_patient')), " +
        "(SELECT count(*) FROM analysis.analysis_task), " +
        "(SELECT count(*) FROM analysis.task_input_snapshot), " +
        "(SELECT count(*) FROM analysis.task_input_snapshot WHERE content_hash ~ '^[a-f0-9]{64}$'), " +
        "(SELECT count(*) FROM analysis.health_advice), " +
        "(SELECT count(*) FROM analysis.advice_evidence), " +
        "(SELECT count(*) FROM analysis.advice_callback), " +
        "(SELECT count(*) FROM analysis.advice_feedback), " +
        "(SELECT count(*) FROM analysis.advice_feedback_event), " +
        "(SELECT count(*) FROM pg_class WHERE oid IN " +
        "('analysis.health_advice'::regclass, 'analysis.advice_evidence'::regclass, " +
        "'analysis.advice_callback'::regclass, 'analysis.advice_feedback'::regclass, " +
        "'analysis.advice_feedback_event'::regclass, 'health.notification_preference'::regclass, " +
        "'health.notification_outbox'::regclass, 'health.patient_notification'::regclass, " +
        "'health.activity_record'::regclass, 'health.mood_record'::regclass) AND relrowsecurity AND relforcerowsecurity), " +
        "(SELECT count(*) FROM health.notification_outbox), " +
        "(SELECT count(*) FROM health.patient_notification), " +
        "(SELECT count(*) FROM health.activity_record WHERE activity_type='walking' AND duration_minutes=30), " +
        "(SELECT count(*) FROM health.mood_record WHERE patient_id='$moodPatientId' AND mood_level=4 " +
        "AND jsonb_array_length(emotion_tags)=2 AND emotion_tags->>0='calm' " +
        "AND emotion_tags->>1='content' AND note='synthetic restore evidence')"
    $evidence = (& $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d $restoreDb -At -v ON_ERROR_STOP=1 -c $evidenceSql) -join ''
    if ($LASTEXITCODE -ne 0) { throw 'Restored data/constraint query failed.' }
    $fields = $evidence.Trim().Split('|')
    if ($fields.Count -ne 17 -or [int]$fields[0] -lt 1 -or [int]$fields[1] -lt 1 `
        -or [int]$fields[2] -lt 1 -or [int]$fields[3] -lt 2 `
        -or [int]$fields[4] -lt 1 -or [int]$fields[5] -lt 1 `
        -or [int]$fields[6] -lt [int]$fields[5] -or [int]$fields[7] -lt 1 `
        -or [int]$fields[8] -lt 1 -or [int]$fields[9] -lt 1 `
        -or [int]$fields[10] -lt 1 -or [int]$fields[11] -lt 1 `
        -or [int]$fields[12] -ne 10 -or [int]$fields[13] -lt 1 -or [int]$fields[14] -lt 1 `
        -or [int]$fields[15] -lt 1 -or [int]$fields[16] -ne 1) {
        throw "Restored F06 row/constraint evidence is incomplete: $evidence"
    }

    $query = (& $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d $restoreDb -At -v ON_ERROR_STOP=1 `
        -c 'SELECT count(*) FROM health.medication_plan p LEFT JOIN health.medication_source_ref s ON s.id=p.source_ref_id AND s.patient_id=p.patient_id') -join ''
    if ($LASTEXITCODE -ne 0 -or [int]$query.Trim() -lt 1) {
        throw 'Restored application query did not return medication plans.'
    }
    Write-Output "PostgreSQL 18 backup/restore rehearsal passed: revision=$revision, medication_plans=$($fields[0]), tombstones=$($fields[1]), idempotency_rows=$($fields[2]), ownership_constraints=$($fields[3]), analysis_tasks=$($fields[4]), snapshots=$($fields[5]), valid_snapshot_hashes=$($fields[6]), advice=$($fields[7]), advice_evidence=$($fields[8]), advice_callbacks=$($fields[9]), advice_feedback=$($fields[10]), advice_feedback_events=$($fields[11]), forced_rls_tables=$($fields[12]), notification_outbox=$($fields[13]), patient_notifications=$($fields[14]), mood_records=$($fields[16])."
    Write-Output 'PostgreSQL 18 backup/restore rehearsal command completed successfully.'
}
finally {
    if ($restoreBucket -and $env:PRIVACY_S3_ENDPOINT) {
        $removeRestoreBucket = @'
import os, boto3
from botocore.config import Config
c=boto3.client('s3',endpoint_url=os.environ['PRIVACY_S3_ENDPOINT'],aws_access_key_id=os.environ['PRIVACY_S3_ACCESS_KEY'],aws_secret_access_key=os.environ['PRIVACY_S3_SECRET_KEY'],config=Config(s3={'addressing_style':'path'}))
b=os.environ['PRIVACY_RESTORE_BUCKET']
try:
    r=c.list_object_versions(Bucket=b)
    for v in r.get('Versions',[])+r.get('DeleteMarkers',[]): c.delete_object(Bucket=b,Key=v['Key'],VersionId=v['VersionId'])
    c.delete_bucket(Bucket=b)
except c.exceptions.NoSuchBucket: pass
'@
        Push-Location (Join-Path $PSScriptRoot '..\backend')
        try { & $uv run --locked --project . --python $python python -c $removeRestoreBucket | Out-Null } finally { Pop-Location }
    }
    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        psql -U gutcare_bootstrap -d postgres -v ON_ERROR_STOP=1 `
        -c "DROP DATABASE IF EXISTS $restoreDb WITH (FORCE)" 2>$null | Out-Null
    & $docker.Source compose -f $composeFile -p $project exec -T $service `
        rm -f $backupPath 2>$null | Out-Null
}
