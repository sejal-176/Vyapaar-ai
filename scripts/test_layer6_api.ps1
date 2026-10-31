# Script to start uvicorn, make Invoke-RestMethod calls, and terminate uvicorn
$proc = Start-Process python -ArgumentList "-m uvicorn backend.main:app --port 8000" -PassThru
Start-Sleep -Seconds 3

try {
    Write-Host "==================== POST /api/cases ===================="
    $createBody = @{
        case_type = "MISMATCH"
        description = "Customer claimed Rs 250 paid, ledger recorded Rs 50"
        status = "OPEN"
        related_reference = "202610259999"
        note = "Follow up with customer"
    } | ConvertTo-Json

    $case = Invoke-RestMethod -Uri "http://localhost:8000/api/cases?merchant_id=1" -Method Post -ContentType "application/json" -Body $createBody
    $case | ConvertTo-Json

    $caseId = $case.id

    Write-Host "`n==================== GET /api/cases ===================="
    $cases = Invoke-RestMethod -Uri "http://localhost:8000/api/cases?merchant_id=1" -Method Get
    Write-Host "Total cases returned for merchant 1: $($cases.Length)"
    Write-Host "First case:"
    $cases[0] | ConvertTo-Json

    Write-Host "`n==================== PATCH /api/cases/{id} ===================="
    $patchBody = @{
        status = "UNDER_REVIEW"
        note = "Customer receipt provided; checking with bank"
    } | ConvertTo-Json

    $patched = Invoke-RestMethod -Uri "http://localhost:8000/api/cases/$caseId`?merchant_id=1" -Method Patch -ContentType "application/json" -Body $patchBody
    $patched | ConvertTo-Json

    Write-Host "`n==================== GET /api/report ===================="
    $report = Invoke-RestMethod -Uri "http://localhost:8000/api/report?merchant_id=1" -Method Get
    Write-Host "Report Date: $($report.date)"
    Write-Host "`nSections -> Summary:"
    $report.sections.summary | ConvertTo-Json
    Write-Host "`nSections -> Comparison:"
    $report.sections.comparison | ConvertTo-Json
    Write-Host "`nSections -> Peak Hour:"
    $report.sections.peak_hour | ConvertTo-Json
    Write-Host "`nSections -> Open Cases: $($report.sections.open_cases)"
    Write-Host "`nPre-rendered Plain Text Report:"
    Write-Host $report.text
}
finally {
    Stop-Process -Id $proc.Id -Force
}

