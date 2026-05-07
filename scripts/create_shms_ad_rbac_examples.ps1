<#
.SYNOPSIS
Creates all-tenant viewer groups via AD nesting and a small set of example users.

.DESCRIPTION
Implements the recommended "option 1" shortcut model for SHMS Nautobot RBAC:

- Creates umbrella security groups:
  - NB-ALLTENANTS-OPS-USERS
  - NB-ALLTENANTS-NONOPS-USERS
- Nests those groups into each tenant-specific viewer group:
  - NB-<TENANT>-OPS-USERS
  - NB-<TENANT>-NONOPS-USERS
- Creates example viewer users and assigns them to the correct groups:
  - ops viewer for all tenants
  - non-ops viewer for all tenants
  - ops viewer for Zenith
  - non-ops viewer for AXEPA

This script is idempotent:
- existing OUs are reused
- existing groups are reused
- existing users are updated/enabled
- existing group memberships are left in place

.NOTES
Requires the ActiveDirectory PowerShell module and rights to manage AD users/groups.
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
    [string]$UserPath = "CN=Users,DC=shms,DC=local",

    [Parameter()]
    [string]$UserPassword = "P@ssw0rd!",

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

function Assert-GroupExists {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    $group = Get-GroupByName -Name $Name
    if (-not $group) {
        throw "Required AD group '$Name' does not exist. Run create_shms_ad_rbac_groups.ps1 first."
    }

    return $group
}

function Get-PrincipalByIdentity {
    param(
        [Parameter(Mandatory)]
        [string]$Identity
    )

    try {
        return Get-ADGroup -Identity $Identity -ErrorAction Stop
    }
    catch {
    }

    try {
        return Get-ADUser -Identity $Identity -ErrorAction Stop
    }
    catch {
    }

    try {
        return Get-ADObject -LDAPFilter "(|(sAMAccountName=$Identity)(name=$Identity))" -ErrorAction Stop | Select-Object -First 1
    }
    catch {
        return $null
    }
}

function Ensure-GroupMembership {
    param(
        [Parameter(Mandatory)]
        [string]$ParentGroup,

        [Parameter(Mandatory)]
        [string]$Member
    )

    $memberObject = Get-PrincipalByIdentity -Identity $Member

    $currentMembers = @(Get-ADGroupMember -Identity $ParentGroup -Recursive:$false -ErrorAction Stop)
    $current = $currentMembers | Where-Object {
        $_.Name -eq $Member -or
        ($memberObject -and $_.DistinguishedName -eq $memberObject.DistinguishedName)
    }

    if ($current) {
        Write-Host "Membership exists: $Member -> $ParentGroup"
        return
    }

    if ($PSCmdlet.ShouldProcess("$Member -> $ParentGroup", "Add AD group membership")) {
        Write-Host "Adding membership: $Member -> $ParentGroup"
        Add-ADGroupMember -Identity $ParentGroup -Members $Member
    }
}

function Get-UserBySam {
    param(
        [Parameter(Mandatory)]
        [string]$SamAccountName
    )

    try {
        return Get-ADUser -Identity $SamAccountName -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Ensure-User {
    param(
        [Parameter(Mandatory)]
        [string]$SamAccountName,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$GivenName,

        [Parameter(Mandatory)]
        [string]$Surname,

        [Parameter(Mandatory)]
        [string]$Description
    )

    $existing = Get-UserBySam -SamAccountName $SamAccountName
    $securePassword = ConvertTo-SecureString $UserPassword -AsPlainText -Force

    if (-not $existing) {
        if ($PSCmdlet.ShouldProcess($SamAccountName, "Create AD user")) {
            Write-Host "Creating user: $SamAccountName"
            New-ADUser `
                -SamAccountName $SamAccountName `
                -UserPrincipalName "$SamAccountName@shms.local" `
                -Name $Name `
                -DisplayName $Name `
                -GivenName $GivenName `
                -Surname $Surname `
                -Description $Description `
                -Enabled $true `
                -Path $UserPath `
                -AccountPassword $securePassword `
                -ChangePasswordAtLogon $false
        }

        return Get-UserBySam -SamAccountName $SamAccountName
    }

    if ($PSCmdlet.ShouldProcess($SamAccountName, "Update AD user password and enable account")) {
        Write-Host "Updating user: $SamAccountName"
        Set-ADAccountPassword -Identity $SamAccountName -Reset -NewPassword $securePassword
        Enable-ADAccount -Identity $SamAccountName
    }

    return $existing
}

Assert-ActiveDirectoryModule
Ensure-OrganizationalUnitPath -DistinguishedName $DirectoryRootDN | Out-Null

$nautobotDn = "OU=$NautobotOuName,$DirectoryRootDN"
$tenantAccessDn = "OU=TenantAccess,$nautobotDn"
$allTenantsDn = "OU=AllTenants,$tenantAccessDn"

Ensure-OrganizationalUnit -Name $NautobotOuName -Path $DirectoryRootDN | Out-Null
Ensure-OrganizationalUnit -Name "TenantAccess" -Path $nautobotDn | Out-Null
Ensure-OrganizationalUnit -Name "AllTenants" -Path $tenantAccessDn | Out-Null

$loginGroup = Assert-GroupExists -Name "NB-LOGIN"
$allTenantsOpsUsers = Ensure-Group `
    -Name "NB-ALLTENANTS-OPS-USERS" `
    -Path $allTenantsDn `
    -Description "Umbrella group for operational viewer access across all tenants."

$allTenantsNonOpsUsers = Ensure-Group `
    -Name "NB-ALLTENANTS-NONOPS-USERS" `
    -Path $allTenantsDn `
    -Description "Umbrella group for non-operational viewer access across all tenants."

foreach ($tenantName in $TenantNames) {
    $tenantKey = ConvertTo-TenantKey -Name $tenantName
    $tenantOpsUsers = Assert-GroupExists -Name "NB-$tenantKey-OPS-USERS"
    $tenantNonOpsUsers = Assert-GroupExists -Name "NB-$tenantKey-NONOPS-USERS"

    Ensure-GroupMembership -ParentGroup $tenantOpsUsers.SamAccountName -Member $allTenantsOpsUsers.SamAccountName
    Ensure-GroupMembership -ParentGroup $tenantNonOpsUsers.SamAccountName -Member $allTenantsNonOpsUsers.SamAccountName
}

$exampleUsers = @(
    @{
        Sam = "nb.ops.all.viewer"
        Name = "NB Ops All Viewer"
        Given = "NB"
        Surname = "OpsAllViewer"
        Description = "Operational viewer across all tenants."
        Groups = @("NB-LOGIN", "NB-ALLTENANTS-OPS-USERS")
    },
    @{
        Sam = "nb.nonops.all.viewer"
        Name = "NB NonOps All Viewer"
        Given = "NB"
        Surname = "NonOpsAllViewer"
        Description = "Non-operational viewer across all tenants."
        Groups = @("NB-LOGIN", "NB-ALLTENANTS-NONOPS-USERS")
    },
    @{
        Sam = "nb.zenith.ops.viewer"
        Name = "NB Zenith Ops Viewer"
        Given = "NB"
        Surname = "ZenithOpsViewer"
        Description = "Operational viewer for Zenith only."
        Groups = @("NB-LOGIN", "NB-ZENITH-OPS-USERS")
    },
    @{
        # Keep the logon name within conservative AD account-name limits.
        Sam = "nb_axepa_nonops_vw"
        Name = "NB AXEPA NonOps Viewer"
        Given = "NB"
        Surname = "AxepaNonOpsViewer"
        Description = "Non-operational viewer for AXEPA only."
        Groups = @("NB-LOGIN", "NB-AXEPA-NONOPS-USERS")
    }
)

foreach ($user in $exampleUsers) {
    Ensure-User `
        -SamAccountName $user.Sam `
        -Name $user.Name `
        -GivenName $user.Given `
        -Surname $user.Surname `
        -Description $user.Description | Out-Null

    foreach ($groupName in $user.Groups) {
        Assert-GroupExists -Name $groupName | Out-Null
        Ensure-GroupMembership -ParentGroup $groupName -Member $user.Sam
    }
}

Write-Host ""
Write-Host "Completed umbrella-group nesting and example-user creation."
Write-Host "Created/ensured umbrella groups:"
Write-Host "  - NB-ALLTENANTS-OPS-USERS"
Write-Host "  - NB-ALLTENANTS-NONOPS-USERS"
Write-Host "Created/updated example users with password '$UserPassword':"
Write-Host "  - nb.ops.all.viewer"
Write-Host "  - nb.nonops.all.viewer"
Write-Host "  - nb.zenith.ops.viewer"
Write-Host "  - nb_axepa_nonops_vw"
