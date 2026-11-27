// CI on Jenkins: a thin wrapper around scripts/ci/run-tier.sh (CONTRIBUTING.md, CI tiers).
//
// A Multibranch Pipeline builds branches and change requests. The tier comes from the build:
// a branch build runs fast, a change request full, the default branch full after a merge, and the
// nightly timer on the default branch runs nightly. The TIER parameter overrides it.
// Every stage runs one job of scripts/ci/checks.toml through scripts/ci/jenkins/run-job.sh. The
// stages build the Dev Container image of .devcontainer/ without the J-Link software
// (CRUX_JLINK=0), except the Dev container job, which builds the image itself with
// scripts/dev-shell.sh and so runs on an agent labelled docker with Docker and Python 3.11 or later.
// The repository is checked out as <stage workspace>/crux-controller, the layout the checks expect.
// This file has not run on a Jenkins server.

// Runs one job, publishes its JUnit report and the check logs, then removes the stage's workspace,
// which also holds the west workspace of the job.
def runJob(String job) {
    try {
        sh "scripts/ci/jenkins/run-job.sh ${job}"
    } finally {
        junit allowEmptyResults: true, testResults: 'build/ci/*.junit.xml'
        archiveArtifacts allowEmptyArchive: true, artifacts: 'build/ci/**'
        dir('..') {
            deleteDir()
        }
    }
}

pipeline {
    agent none
    parameters {
        choice(name: 'TIER', choices: ['auto', 'fast', 'full', 'nightly'],
               description: 'CI tier (CONTRIBUTING.md, CI tiers). auto decides from the build.')
    }
    triggers {
        cron(env.BRANCH_NAME == 'main' ? 'H 2 * * *' : '')
    }
    options {
        disableConcurrentBuilds(abortPrevious: env.BRANCH_NAME != 'main')
        timeout(time: 3, unit: 'HOURS')
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }
    environment {
        TIER = "${params.TIER ?: 'auto'}"
        CRUX_CI_TRIGGER = "${currentBuild.getBuildCauses('hudson.triggers.TimerTrigger$TimerTriggerCause') ? 'timer' : ''}"
        SDK_VERSION = '1.0.1'
        ZEPHYR_SDK_INSTALL_DIR = '/opt/crux-cache/sdk/zephyr-sdk-1.0.1'
    }
    stages {
        stage('Checks') {
            parallel {
                stage('tooling') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/tooling/crux-controller" } }
                    steps { script { runJob('tooling') } }
                }
                stage('pins') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/pins/crux-controller" } }
                    steps { script { runJob('pins') } }
                }
                stage('host-OFF') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/host-OFF/crux-controller" } }
                    steps { script { runJob('host-OFF') } }
                }
                stage('host-ON') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/host-ON/crux-controller" } }
                    steps { script { runJob('host-ON') } }
                }
                stage('workload') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/workload/crux-controller" } }
                    steps { script { runJob('workload') } }
                }
                stage('net') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/net/crux-controller" } }
                    steps { script { runJob('net') } }
                }
                stage('file') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/file/crux-controller" } }
                    steps { script { runJob('file') } }
                }
                stage('system') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/system/crux-controller" } }
                    steps { script { runJob('system') } }
                }
                stage('sntp') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/sntp/crux-controller" } }
                    steps { script { runJob('sntp') } }
                }
                stage('management') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/management/crux-controller" } }
                    steps { script { runJob('management') } }
                }
                stage('boundary') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/boundary/crux-controller" } }
                    steps { script { runJob('boundary') } }
                }
                stage('patch-style') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/patch-style/crux-controller" } }
                    steps { script { runJob('patch-style') } }
                }
                stage('minimal') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/minimal/crux-controller" } }
                    steps { script { runJob('minimal') } }
                }
                stage('base') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/base/crux-controller" } }
                    steps { script { runJob('base') } }
                }
                stage('static') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/static/crux-controller" } }
                    steps { script { runJob('static') } }
                }
                stage('budget-minimal') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-minimal/crux-controller" } }
                    steps { script { runJob('budget-minimal') } }
                }
                stage('budget-workload') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-workload/crux-controller" } }
                    steps { script { runJob('budget-workload') } }
                }
                stage('budget-net') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-net/crux-controller" } }
                    steps { script { runJob('budget-net') } }
                }
                stage('budget-file') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-file/crux-controller" } }
                    steps { script { runJob('budget-file') } }
                }
                stage('budget-system') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-system/crux-controller" } }
                    steps { script { runJob('budget-system') } }
                }
                stage('budget-sntp') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-sntp/crux-controller" } }
                    steps { script { runJob('budget-sntp') } }
                }
                stage('budget-management') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-management/crux-controller" } }
                    steps { script { runJob('budget-management') } }
                }
                stage('budget-base') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/budget-base/crux-controller" } }
                    steps { script { runJob('budget-base') } }
                }
                stage('devcontainer') {
                    agent { node { label 'docker'; customWorkspace "crux-ci/${env.BUILD_TAG}/devcontainer/crux-controller" } }
                    steps { script { runJob('devcontainer') } }
                }
                stage('rebuild') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/rebuild/crux-controller" } }
                    steps { script { runJob('rebuild') } }
                }
                stage('release') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/release/crux-controller" } }
                    steps { script { runJob('release') } }
                }
                stage('scheduled-main') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/scheduled-main/crux-controller" } }
                    steps { script { runJob('scheduled-main') } }
                }
                stage('product-integration') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/product-integration/crux-controller" } }
                    steps { script { runJob('product-integration') } }
                }
                stage('template') {
                    agent { dockerfile { filename 'Dockerfile'; dir '.devcontainer'; additionalBuildArgs '--build-arg CRUX_JLINK=0'; args '-v crux-controller-ci-cache:/opt/crux-cache'; customWorkspace "crux-ci/${env.BUILD_TAG}/template/crux-controller" } }
                    steps { script { runJob('template') } }
                }
            }
        }
    }
}
