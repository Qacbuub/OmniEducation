# Points the Docker copy at a public address (used by public-link.bat): Django accepts the host name and
# emails link to it. Keeps every other line of .env.prod, including passwords and email settings.
param([Parameter(Mandatory = $true)][string]$PublicHost, [string]$Port = "80")
$ErrorActionPreference = "Stop"
$f = Join-Path (Get-Location) ".env.prod"
$lines = [IO.File]::ReadAllLines($f)
$local = "http://localhost"
if ($Port -ne "80") { $local = "$local`:$Port" }
$public = "https://$PublicHost"
$values = @{
  "DJANGO_ALLOWED_HOSTS"        = "localhost,127.0.0.1,$PublicHost"
  "FRONTEND_URL"                = $public
  "CORS_ALLOWED_ORIGINS"        = "$public,$local"
  "DJANGO_CSRF_TRUSTED_ORIGINS" = "$public,$local"
}
$seen = @{}
$out = foreach ($l in $lines) {
  $k = ($l -split "=", 2)[0].Trim()
  if ($values.ContainsKey($k) -and -not $l.TrimStart().StartsWith("#")) { $seen[$k] = $true; "$k=$($values[$k])" } else { $l }
}
foreach ($k in $values.Keys) { if (-not $seen[$k]) { $out += "$k=$($values[$k])" } }
[IO.File]::WriteAllText($f, (($out -join "`n") + "`n"))
Write-Host "Settings updated for $public"
