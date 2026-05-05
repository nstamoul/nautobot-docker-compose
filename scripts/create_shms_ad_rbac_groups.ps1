<#
.SYNOPSIS
Creates the SHMS Nautobot AD OU structure and security groups for selected tenants.

.DESCRIPTION
Builds the OU structure and security groups for the composite RBAC model used by
SHMS Nautobot:

- Platform flag groups:
  - NB-LOGIN
  - NB-STAFF
  - NB-SUPERUSERS
- Tenant entitlement groups:
  - NB-<TENANTKEY>-OPS-USERS
  - NB-<TENANTKEY>-OPS-ADMINS
  - NB-<TENANTKEY>-NONOPS-USERS
  - NB-<TENANTKEY>-NONOPS-ADMINS

The script is idempotent:
- existing OUs are reused
- existing groups are left in place

It defaults to the three tenants requested by the user:
- Zenith
- AXEPA
- ENA-ON

.NOTES
Requires the ActiveDirectory PowerShell module and rights to create OUs/groups.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [string]$DirectoryRootDN = "OU=Groups,DC=shms,DC=local",

    [Parameter()]
    [string]$NautobotOuName = "Nautobot",

    [Parameter()]
    [string[]]$TenantNames = @(
        "Zenith",
        "AXEPA",
        "ENA-ON"
    ),

    [Parameter()]
    [ValidateSet("Global", "DomainLocal", "Universal")]
    [string]$GroupScope = "Global",

    [Parameter()]
    [ValidateSet("Security", "Distribution")]
    [string]$GroupCategory = "Security"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-ActiveDirectoryModule {
    if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {
        throw "ActiveDirectory PowerShell module is not available. Run this on a host with RSAT/AD tools installed."
    }

    Import-Module ActiveDirectory -ErrorAction Stop
}

function ConvertTo-TenantKey {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    $upper = $Name.ToUpperInvariant()
    $normalized = $upper -replace "[^A-Z0-9]+", "-"
    $normalized = $normalized -replace "-{2,}", "-"
    $normalized = $normalized.Trim("-")

    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "Unable to derive tenant key from tenant name '$Name'."
    }

    return $normalized
}

function Get-OrganizationalUnit {
    param(
        [Parameter(Mandatory)]
        [string]$DistinguishedName
    )

    try {
        return Get-ADOrganizationalUnit -Identity $DistinguishedName -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Ensure-OrganizationalUnit {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Path
    )

    $dn = "OU=$Name,$Path"
    $existing = Get-OrganizationalUnit -DistinguishedName $dn
    if ($existing) {
        Write-Host "OU exists: $dn"
        return $existing
    }

    if ($PSCmdlet.ShouldProcess($dn, "Create OU")) {
        Write-Host "Creating OU: $dn"
        return New-ADOrganizationalUnit -Name $Name -Path $Path -ProtectedFromAccidentalDeletion $true
    }

    return $null
}

function Ensure-OrganizationalUnitPath {
    param(
        [Parameter(Mandatory)]
        [string]$DistinguishedName
    )

    $parts = $DistinguishedName -split "\s*,\s*"
    $domainParts = @($parts | Where-Object { $_ -like "DC=*" })
    if (-not $domainParts) {
        throw "Distinguished name '$DistinguishedName' does not contain a domain component."
    }

    $ouParts = @($parts | Where-Object { $_ -like "OU=*" })
    if (-not $ouParts) {
        return $null
    }

    [array]::Reverse($ouParts)

    $currentPath = $domainParts -join ","
    foreach ($ouPart in $ouParts) {
        $ouName = $ouPart.Substring(3)
        Ensure-OrganizationalUnit -Name $ouName -Path $currentPath | Out-Null
        $currentPath = "OU=$ouName,$currentPath"
    }

    return Get-OrganizationalUnit -DistinguishedName $DistinguishedName
}

function Get-GroupByName {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    try {
        return Get-ADGroup -Identity $Name -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Ensure-Group {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter()]
        [string]$Description = ""
    )

    $existing = Get-GroupByName -Name $Name
    if ($existing) {
        Write-Host "Group exists: $Name"
        return $existing
    }

    if ($PSCmdlet.ShouldProcess($Name, "Create AD group")) {
        Write-Host "Creating group: $Name"
        return New-ADGroup `
            -Name $Name `
            -SamAccountName $Name `
            -GroupScope $GroupScope `
            -GroupCategory $GroupCategory `
            -Path $Path `
            -DisplayName $Name `
            -Description $Description
    }

    return $null
}

Assert-ActiveDirectoryModule

Ensure-OrganizationalUnitPath -DistinguishedName $DirectoryRootDN | Out-Null

$nautobotOu = Ensure-OrganizationalUnit -Name $NautobotOuName -Path $DirectoryRootDN
$nautobotDn = "OU=$NautobotOuName,$DirectoryRootDN"

$platformOu = Ensure-OrganizationalUnit -Name "Platform" -Path $nautobotDn
$tenantAccessOu = Ensure-OrganizationalUnit -Name "TenantAccess" -Path $nautobotDn

$platformDn = "OU=Platform,$nautobotDn"
$tenantAccessDn = "OU=TenantAccess,$nautobotDn"

$platformGroups = @(
    @{
        Name = "NB-LOGIN"
        Description = "Required for Nautobot login and active account flag."
    },
    @{
        Name = "NB-STAFF"
        Description = "Maps to Nautobot is_staff for operational administrators."
    },
    @{
        Name = "NB-SUPERUSERS"
        Description = "Maps to Nautobot is_superuser for platform owners."
    }
)

foreach ($group in $platformGroups) {
    Ensure-Group -Name $group.Name -Path $platformDn -Description $group.Description | Out-Null
}

foreach ($tenantName in $TenantNames) {
    $tenantKey = ConvertTo-TenantKey -Name $tenantName
    $tenantOu = Ensure-OrganizationalUnit -Name $tenantKey -Path $tenantAccessDn
    $tenantDn = "OU=$tenantKey,$tenantAccessDn"

    $tenantGroups = @(
        @{
            Name = "NB-$tenantKey-OPS-USERS"
            Description = "Tenant-scoped operational read access for $tenantName."
        },
        @{
            Name = "NB-$tenantKey-OPS-ADMINS"
            Description = "Tenant-scoped operational add/change access for $tenantName."
        },
        @{
            Name = "NB-$tenantKey-NONOPS-USERS"
            Description = "Tenant-scoped non-operational read access for $tenantName."
        },
        @{
            Name = "NB-$tenantKey-NONOPS-ADMINS"
            Description = "Tenant-scoped non-operational add/change access for $tenantName."
        }
    )

    foreach ($group in $tenantGroups) {
        Ensure-Group -Name $group.Name -Path $tenantDn -Description $group.Description | Out-Null
    }
}

Write-Host ""
Write-Host "Completed SHMS Nautobot AD OU/group bootstrap."
Write-Host "Root OU: $nautobotDn"
Write-Host "Platform groups path: $platformDn"
Write-Host "Tenant access groups path: $tenantAccessDn"
Write-Host "Tenants processed: $($TenantNames -join ', ')"
