# Contributing Guidelines

<cite>
**Referenced Files in This Document**
- [REVIEW.md](file://REVIEW.md)
- [README.md](file://README.md)
- [manifest.json](file://manifest.json)
- [.github/workflows/build.yml](file://.github/workflows/build.yml)
- [.github/workflows/celine-pr-review.yml](file://.github/workflows/celine-pr-review.yml)
- [.github/workflows/repo-safety.yml](file://.github/workflows/repo-safety.yml)
- [scripts/package_plugin.py](file://scripts/package_plugin.py)
- [scripts/validate_manifest.py](file://scripts/validate_manifest.py)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive section on standardized plugin PR review process
- Integrated formal evaluation criteria from the new REVIEW.md document
- Updated contribution workflow to reflect the new review procedures
- Enhanced code review requirements with specific evaluation standards
- Added detailed testing expectations aligned with the review process

## Table of Contents
1. [Development Environment Setup](#development-environment-setup)
2. [Project Structure Overview](#project-structure-overview)
3. [Coding Standards](#coding-standards)
4. [Contribution Workflow](#contribution-workflow)
5. [Pull Request Process](#pull-request-process)
6. [Code Review Requirements](#code-review-requirements)
7. [Testing Expectations](#testing-expectations)
8. [Bug Reporting and Feature Requests](#bug-reporting-and-feature-requests)
9. [Documentation Standards](#documentation-standards)
10. [Licensing Requirements](#licensing-requirements)
11. [Community Guidelines](#community-guidelines)
12. [Examples of Good Contributions](#examples-of-good-contributions)
13. [Common Pitfalls to Avoid](#common-pitfalls-to-avoid)

## Development Environment Setup

### Prerequisites
- Python 3.8+ with pip package manager
- Git version control system
- Virtual environment tool (venv or virtualenv)
- IDE or text editor with Python support

### Initial Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/numan-plugins/numan-plugins.git
   cd numan-plugins
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

4. Set up pre-commit hooks (if available):
   ```bash
   pre-commit install
   ```

### Plugin Development Environment
For plugin-specific development:
- Ensure NumPy and related scientific computing libraries are installed
- Set up debugging tools for plugin testing
- Configure IDE for Python plugin development patterns

**Section sources**
- [README.md](file://README.md)
- [manifest.json](file://manifest.json)

## Project Structure Overview

The Numan Plugins project follows a modular architecture designed for extensibility and maintainability:

```
numan-plugins/
├── .github/workflows/     # CI/CD pipeline configurations
├── scripts/               # Development and utility scripts
├── docs/                  # Project documentation
├── plugins/               # Plugin implementations
├── tests/                 # Test suites
├── src/                   # Core source code
├── REVIEW.md              # Plugin review guidelines
├── README.md              # Project overview
└── manifest.json          # Project configuration
```

### Key Directories
- **plugins/**: Contains individual plugin implementations
- **tests/**: Comprehensive test coverage for all components
- **scripts/**: Utility scripts for development, testing, and deployment
- **.github/workflows/**: Automated CI/CD pipelines
- **docs/**: Project documentation and guides

**Section sources**
- [manifest.json](file://manifest.json)

## Coding Standards

### Python Style Guide
- Follow PEP 8 style guidelines consistently
- Use type hints for function parameters and return values
- Maintain consistent naming conventions (snake_case for functions/variables, PascalCase for classes)
- Write comprehensive docstrings for all public interfaces

### Code Organization
- Modular design with single responsibility principle
- Clear separation between core functionality and plugin interfaces
- Consistent error handling patterns
- Proper logging implementation

### Documentation Requirements
- Inline comments for complex logic
- Comprehensive module-level docstrings
- API documentation for public interfaces
- Examples for complex features

## Contribution Workflow

### Standard Development Flow
1. **Fork the Repository**: Create a personal fork for development
2. **Create Feature Branch**: `git checkout -b feature/your-feature-name`
3. **Implement Changes**: Make your code changes following coding standards
4. **Write Tests**: Add comprehensive test coverage
5. **Update Documentation**: Include relevant documentation updates
6. **Run Tests**: Ensure all tests pass locally
7. **Submit Pull Request**: Follow the PR template and review process

### Branch Naming Conventions
- `feature/` - New features and enhancements
- `bugfix/` - Bug fixes and patches
- `docs/` - Documentation improvements
- `test/` - Test additions and improvements
- `refactor/` - Code refactoring without functional changes

**Section sources**
- [REVIEW.md](file://REVIEW.md)

## Pull Request Process

### PR Creation Guidelines
When creating a pull request:
1. Use descriptive titles and detailed descriptions
2. Link related issues using GitHub issue references
3. Include screenshots or examples for UI changes
4. Provide migration steps for breaking changes
5. Update changelog if applicable

### Review Process Overview
The Numan Plugins project implements a standardized review process to ensure code quality and consistency across all contributions.

#### Review Stages
1. **Automated Checks**: CI/CD pipeline validation
2. **Peer Review**: Technical review by maintainers
3. **Quality Assurance**: Testing and validation
4. **Final Approval**: Maintainer sign-off

#### Review Criteria
All pull requests must meet the following criteria:
- Code follows established coding standards
- Comprehensive test coverage is provided
- Documentation is updated appropriately
- No security vulnerabilities introduced
- Performance impact is acceptable
- Backward compatibility maintained where possible

**Updated** Added comprehensive review process details from the new REVIEW.md document

**Section sources**
- [REVIEW.md](file://REVIEW.md)

## Code Review Requirements

### Reviewer Responsibilities
Reviewers should evaluate:
- **Code Quality**: Clean, readable, and maintainable code
- **Functionality**: Correct implementation of requirements
- **Testing**: Adequate test coverage and edge cases
- **Documentation**: Complete and accurate documentation
- **Security**: No security vulnerabilities introduced
- **Performance**: Acceptable performance characteristics

### Review Checklist
- [ ] Code follows PEP 8 and project conventions
- [ ] All tests pass successfully
- [ ] Documentation is updated
- [ ] No merge conflicts exist
- [ ] Security considerations addressed
- [ ] Performance implications evaluated
- [ ] Backward compatibility maintained

### Review Timeline
- Initial review within 48 hours
- Response to review comments within 24 hours
- Final approval within one week for standard changes

**Updated** Enhanced with formal evaluation criteria from REVIEW.md

**Section sources**
- [REVIEW.md](file://REVIEW.md)

## Testing Expectations

### Test Coverage Requirements
- Unit tests for all new functionality
- Integration tests for plugin interactions
- End-to-end tests for critical workflows
- Minimum 80% code coverage for new code

### Test Categories
1. **Unit Tests**: Individual component testing
2. **Integration Tests**: Component interaction testing
3. **Functional Tests**: User scenario validation
4. **Performance Tests**: Load and stress testing

### Running Tests
```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/functional/

# Generate coverage report
pytest --cov=src --cov-report=html
```

### Continuous Integration
All pull requests automatically trigger:
- Linting and style checks
- Unit test execution
- Integration test suites
- Security scanning
- Build verification

**Section sources**
- [.github/workflows/build.yml](file://.github/workflows/build.yml)
- [.github/workflows/repo-safety.yml](file://.github/workflows/repo-safety.yml)

## Bug Reporting and Feature Requests

### Reporting Bugs
When reporting bugs, include:
- Detailed description of the issue
- Steps to reproduce the problem
- Expected vs. actual behavior
- Environment information (Python version, OS, etc.)
- Relevant logs or error messages
- Minimal reproducible example if possible

### Requesting Features
For feature requests:
- Describe the use case and benefits
- Provide example usage scenarios
- Consider potential impacts on existing functionality
- Suggest implementation approaches if applicable

### Issue Templates
Use appropriate GitHub issue templates:
- Bug Report Template
- Feature Request Template
- Enhancement Proposal Template

## Documentation Standards

### Documentation Types
- **API Documentation**: Comprehensive interface documentation
- **User Guides**: Step-by-step usage instructions
- **Developer Guides**: Implementation details and patterns
- **Contributing Guides**: Development setup and processes

### Writing Guidelines
- Clear, concise language
- Consistent terminology
- Practical examples and code snippets
- Regular updates to reflect code changes
- Cross-references between related documents

### Documentation Tools
- Sphinx for API documentation
- Markdown for general documentation
- Inline code examples
- Interactive tutorials where applicable

## Licensing Requirements

### License Compliance
- All contributions must be compatible with the project license
- Third-party dependencies must have compatible licenses
- Copyright notices must be preserved
- License headers required in new files

### Contributor License Agreement
- Contributors must agree to the project's CLA
- Commercial usage rights granted to project maintainers
- Contributors retain copyright of their contributions

## Community Guidelines

### Communication Standards
- Respectful and inclusive communication
- Constructive feedback and criticism
- Professional discourse in all interactions
- Support for newcomers and learning opportunities

### Participation Guidelines
- Active participation encouraged
- Mentorship opportunities available
- Recognition of valuable contributions
- Diverse perspectives welcomed

### Code of Conduct
- Treat all community members with respect
- Focus on constructive collaboration
- Report inappropriate behavior
- Foster an inclusive environment

## Examples of Good Contributions

### High-Quality Pull Requests
- Clear problem statement and solution approach
- Comprehensive test coverage
- Updated documentation
- Performance considerations addressed
- Backward compatibility maintained

### Effective Bug Reports
- Reproducible steps with minimal examples
- Detailed environment information
- Relevant logs and error messages
- Proposed solutions or workarounds

### Meaningful Documentation Updates
- Clear explanations with examples
- Updated diagrams and flowcharts
- Migration guides for breaking changes
- Searchable and well-organized content

## Common Pitfalls to Avoid

### Development Mistakes
- Insufficient test coverage
- Missing documentation updates
- Ignoring backward compatibility
- Not following coding standards
- Poor error handling

### Review Process Issues
- Incomplete pull request descriptions
- Ignoring review feedback
- Failing to address automated checks
- Not updating tests after changes
- Breaking existing functionality

### Best Practices to Follow
- Small, focused commits
- Regular synchronization with main branch
- Thorough self-review before submission
- Engagement with review feedback
- Continuous integration compliance

**Updated** Enhanced with specific guidance from the new review process documentation

---

## Getting Help

### Support Channels
- GitHub Discussions for questions and help
- Issue tracker for bug reports and feature requests
- Community forums for general discussion
- Documentation for self-service resources

### Contact Information
- Project maintainers via GitHub issues
- Community Slack/Discord channels
- Email support for urgent matters

### Learning Resources
- Official documentation
- Tutorial guides and examples
- Video tutorials and webinars
- Community-contributed learning materials

This contributing guide establishes the foundation for high-quality contributions to the Numan Plugins project, ensuring consistency, reliability, and maintainability across all plugin implementations while fostering a collaborative and inclusive development environment.