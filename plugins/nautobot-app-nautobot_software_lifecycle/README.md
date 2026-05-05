# Nautobot Software Lifecycle

A Nautobot app for managing software license lifecycle data.

## Overview

The Nautobot Software Lifecycle app provides comprehensive tracking and management of software licenses and their lifecycle information. This app is designed to help organizations maintain visibility into their software assets, contract coverage, end-of-life dates, and warranty information.

Key features include:
- Track software licenses with comprehensive metadata (86+ fields)
- Import license data from Excel files (Cisco IB Report format)
- Filter and manage SOFTWARE product types
- Associate licenses with Nautobot tenants
- Track important dates (coverage end dates, support end dates, warranty expiration)
- Monitor contract and subscription information
- REST API for programmatic access

This POC version focuses on manual Excel file import through Nautobot jobs. Future versions will support direct integration with vendor APIs (e.g., Cisco Smart Licensing) for automated data synchronization.

## Installation

### Prerequisites

- Nautobot 2.4.2 or higher
- Python 3.9 or higher

### Install the App

1. Install the package:

```bash
pip install nautobot-software-lifecycle
```

Or for development:

```bash
cd nautobot-app-nautobot_software_lifecycle
poetry install
```

2. Add the app to your `nautobot_config.py`:

```python
PLUGINS = [
    "nautobot_software_lifecycle",
]
```

3. Run migrations:

```bash
nautobot-server migrate
```

4. Restart Nautobot services:

```bash
systemctl restart nautobot nautobot-worker
```

## Usage

### Importing Software Licenses from Excel

1. Navigate to **Jobs** in the Nautobot UI
2. Find and run the job: **Import Software Licenses from Excel**
3. Provide the following inputs:
   - **Excel File**: Upload your Cisco IB Report (or similar format Excel file)
   - **Tenant**: Select the tenant to associate with the imported licenses
4. Click **Run Job**

The job will:
- Read the Excel file
- Filter records to only include `Product Type = "SOFTWARE"`
- Import all 86 fields from the Excel file
- Create or update license records based on Product ID and Contract Number
- Log import statistics (created, updated, errors)

### Viewing Software Licenses

1. Navigate to **Apps > Software Lifecycle > Software Licenses**
2. Use filters to search by:
   - Tenant
   - Product ID
   - Product Type
   - Coverage status
   - And more...

### Managing Software Licenses

- **Add**: Create new license records manually
- **Edit**: Update existing license information
- **Bulk Edit**: Update multiple licenses at once
- **Delete**: Remove license records

### API Access

The app provides a REST API endpoint:

```bash
# List all licenses
GET /api/plugins/software-lifecycle/software-licenses/

# Get specific license
GET /api/plugins/software-lifecycle/software-licenses/{id}/

# Create license
POST /api/plugins/software-lifecycle/software-licenses/

# Update license
PATCH /api/plugins/software-lifecycle/software-licenses/{id}/

# Delete license
DELETE /api/plugins/software-lifecycle/software-licenses/{id}/
```

## Excel File Format

The app expects an Excel file with the following columns (Cisco IB Report format):

- Serial Number / PAK number
- Coverage
- Covered Line Status
- Business Entity
- Sub Business Entity
- Product Family
- Product ID
- Product Description
- Asset Type
- **Product Type** (must be "SOFTWARE" to be imported)
- And 76 more fields...

Only rows where `Product Type = "SOFTWARE"` will be imported.

## Data Model

The `SoftwareLicense` model includes:

**Core Fields:**
- Tenant (ForeignKey)
- Product ID
- Product Description
- Product Type
- Serial Number / PAK

**Coverage:**
- Coverage status
- Covered Line Start/End Dates
- Contract information

**Dates:**
- Ship Date
- Last Date of Support (LDOS)
- End of Life dates
- Warranty dates
- Contract end dates

**Location:**
- Install site information
- Address details

**Partners:**
- Partner and billing information

**And many more fields for comprehensive license tracking**

## Development

### Setup Development Environment

1. Clone the repository:

```bash
git clone https://github.com/nautobot/nautobot-app-nautobot_software_lifecycle.git
cd nautobot-app-nautobot_software_lifecycle
```

2. Install dependencies:

```bash
poetry install
```

3. Run migrations:

```bash
poetry shell
invoke migrate
```

4. Start development server:

```bash
invoke debug
```

### Running Tests

```bash
invoke unittest
```

### Code Quality

```bash
# Run linting
invoke ruff

# Auto-fix issues
invoke ruff --fix
```

## Future Enhancements

- Direct integration with vendor APIs (Cisco Smart Licensing, etc.)
- Automated license data synchronization
- License expiration alerts and notifications
- Dashboard widgets for license metrics
- Advanced reporting and analytics
- License compliance checks
- Multi-vendor support

## Contributing

Contributions are welcome! Please see the contributing guidelines for more information.

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Questions?

For questions or support, please open an issue on GitHub.
