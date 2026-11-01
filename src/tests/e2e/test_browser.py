"""Browser-level tests for core local web UI and accessibility behavior."""


# Copyright 2026 Tom Masterson <kd7cyu@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import csv
import io
import os
import shutil
import uuid
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as conditions
from selenium.webdriver.support.ui import WebDriverWait

from chirp_web import chirp_common


_BROWSER_NAMES = tuple(
    name for name in os.environ.get(
        'CHIRP_WEB_BROWSERS', 'chromium,firefox').split(',')
    if name in {'chromium', 'firefox'})


def _channel_csv():
    """Return an accepted CSV image with one populated channel."""
    memory = chirp_common.Memory(0)
    memory.name = 'BROWSER'
    memory.freq = 146520000
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    fields = [field for field in chirp_common.Memory.CSV_FORMAT
              if field != 'Power']
    writer.writerow(fields)
    writer.writerow([
        value for field, value in zip(
            chirp_common.Memory.CSV_FORMAT, memory.to_csv())
        if field != 'Power'
    ])
    return output.getvalue()


@pytest.fixture(params=_BROWSER_NAMES)
def browser(request, running_web_app):
    """Open a supported headless browser against the installed application."""
    browser_name = request.param
    if browser_name == 'firefox':
        driver_path = shutil.which('geckodriver')
        browser_path = next((
            path for path in (
                '/snap/firefox/current/usr/lib/firefox/firefox',
                shutil.which('firefox'),
                shutil.which('firefox-esr'),
            ) if path and os.path.isfile(path)), None)
        if not browser_path or not driver_path:
            pytest.skip(
                    'Firefox system tests require Firefox and GeckoDriver.')
        options = FirefoxOptions()
        options.binary_location = os.path.realpath(browser_path)
        options.add_argument('-headless')
        try:
            driver = webdriver.Firefox(
                service=FirefoxService(driver_path), options=options)
        except WebDriverException as error:
            pytest.skip(f'Could not start Firefox: {error.msg}')
    else:
        driver = _start_chromium()
    driver.set_window_size(1440, 1200)
    driver.implicitly_wait(1)
    driver.get(running_web_app)
    try:
        yield driver
    finally:
        driver.quit()


def _start_chromium():
    """Start Chromium and return a configured Selenium driver."""
    browser_path = next((
        shutil.which(name) for name in
        ('chromium', 'chromium-browser', 'google-chrome')
        if shutil.which(name)), None)
    driver_path = shutil.which('chromedriver')
    if not browser_path or not driver_path:
        pytest.skip('Browser system tests require Chromium and ChromeDriver.')

    options = Options()
    options.binary_location = browser_path
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1440,1200')
    try:
        return webdriver.Chrome(
            service=Service(driver_path), options=options)
    except WebDriverException as error:
        pytest.skip(f'Could not start Chromium: {error.msg}')


def _wait(browser, condition):
    """Wait for a browser condition with a concise test-specific timeout."""
    return WebDriverWait(browser, 10).until(condition)


@pytest.fixture
def file_upload(browser):
    """Upload files through native controls, respecting Firefox sandboxing."""
    copied_files = []

    def upload(control_id, path):
        upload_path = path
        if browser.capabilities['browserName'] == 'firefox':
            upload_path = Path.home() / (
                f'chirp-web-test-{uuid.uuid4().hex}{path.suffix}')
            shutil.copyfile(path, upload_path)
            copied_files.append(upload_path)
        control = browser.find_element(By.ID, control_id)
        browser.execute_script(
            "arguments[0].style.cssText = "
            "'position: static; width: 1px; height: 1px; clip: auto;';",
            control)
        control.send_keys(str(upload_path))

    yield upload

    for path in copied_files:
        path.unlink(missing_ok=True)


def test_browser_channel_edit_workflow(browser, file_upload, tmp_path):
    """Open, edit, and save an image through the rendered browser interface."""
    image = tmp_path / 'browser.csv'
    image.write_text(_channel_csv())

    file_upload('imageFile', image)
    _wait(browser, conditions.text_to_be_present_in_element(
        (By.ID, 'sessionInfo'), 'Generic CSV'))
    _wait(browser, conditions.text_to_be_present_in_element(
        (By.ID, 'memoryRows'), 'BROWSER'))

    browser.find_element(By.CSS_SELECTOR, '.edit-button').click()
    _wait(browser, conditions.visibility_of_element_located(
        (By.ID, 'editDialog')))
    name = browser.find_element(By.CSS_SELECTOR, '#editFields [name="name"]')
    name.clear()
    name.send_keys('SELENIUM')
    browser.find_element(By.ID, 'saveMemory').click()
    _wait(browser, conditions.invisibility_of_element_located(
        (By.ID, 'editDialog')))
    _wait(browser, conditions.text_to_be_present_in_element(
        (By.ID, 'memoryRows'), 'SELENIUM'))

    browser.find_element(By.ID, 'showAbout').click()
    _wait(browser, conditions.visibility_of_element_located(
        (By.ID, 'aboutDialog')))
    close = browser.find_element(By.ID, 'closeAbout')
    close.send_keys(Keys.ENTER)
    _wait(browser, conditions.invisibility_of_element_located(
        (By.ID, 'aboutDialog')))


def test_browser_advanced_diagnostics_are_explicit_and_read_only(
        browser, file_upload, tmp_path):
    """Show the safe trace and require an opt-in for raw driver internals."""
    image = tmp_path / 'diagnostics.csv'
    image.write_text(_channel_csv())
    file_upload('imageFile', image)
    _wait(browser, conditions.text_to_be_present_in_element(
        (By.ID, 'sessionInfo'), 'Generic CSV'))

    browser.find_element(By.ID, 'viewTransferTrace').click()
    _wait(browser, conditions.visibility_of_element_located(
        (By.ID, 'transferTraceDialog')))
    assert 'No serial transfer activity' in browser.find_element(
        By.ID, 'transferTraceContent').text
    browser.find_element(By.ID, 'closeTransferTrace').click()

    browser.find_element(By.ID, 'advancedDiagnostics').click()
    _wait(browser, conditions.visibility_of_element_located(
        (By.ID, 'advancedDiagnosticsDialog')))
    browser.find_element(By.ID, 'enableAdvancedDiagnostics').click()
    browser.find_element(By.ID, 'closeAdvancedDiagnostics').click()
    browser.find_element(
        By.CSS_SELECTOR, '#memoryRows input[type="checkbox"]').click()
    browser.find_element(By.ID, 'advancedDiagnostics').click()
    _wait(browser, conditions.visibility_of_element_located(
        (By.ID, 'advancedDiagnosticsDialog')))
    browser.find_element(By.ID, 'viewRawMemory').click()
    _wait(browser, lambda driver: bool(driver.find_element(
        By.ID, 'rawMemoryContent').text))
    browser.find_element(By.ID, 'closeAdvancedDiagnostics').click()


def test_browser_connection_profiles_are_persisted(browser):
    """Save and load local serial connection details through the profile UI."""
    _wait(browser, conditions.presence_of_element_located(
        (By.ID, 'connectionProfileName')))
    browser.find_element(By.ID, 'connectionProfileName').send_keys('LOCAL')
    manual_port = browser.find_element(By.ID, 'manualSerialPort')
    manual_port.clear()
    manual_port.send_keys('/dev/ttyTEST0')
    browser.find_element(By.ID, 'saveConnectionProfile').click()
    _wait(browser, conditions.text_to_be_present_in_element(
        (By.ID, 'notice'), 'Connection profile saved.'))

    browser.execute_script(
        "document.getElementById('manualSerialPort').value = '/dev/changed';")
    profile = browser.find_element(By.ID, 'connectionProfile')
    browser.execute_script(
        "arguments[0].value = 'LOCAL'; "
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
        profile)
    _wait(browser, lambda driver: not driver.find_element(
        By.ID, 'loadConnectionProfile').get_attribute('disabled'))
    browser.find_element(By.ID, 'loadConnectionProfile').click()
    _wait(browser, lambda driver: driver.find_element(
        By.ID, 'manualSerialPort').get_attribute('value') == '/dev/ttyTEST0')
    stored = browser.execute_script(
        "return JSON.parse(localStorage.getItem("
        "'chirp-web-connection-profiles'));")
    assert stored == [{
        'name': 'LOCAL',
        'radioId': browser.find_element(By.ID, 'radioModel').get_attribute(
            'value'),
        'port': '/dev/ttyTEST0',
        'notes': '',
    }]


def test_browser_ignores_invalid_connection_profile_storage(browser):
    """Keep local profile corruption from blocking the application."""
    browser.execute_script(
        "localStorage.setItem('chirp-web-connection-profiles', '{broken');")
    browser.refresh()
    _wait(browser, conditions.presence_of_element_located(
        (By.ID, 'connectionProfile')))
    assert browser.find_element(By.ID, 'connectionProfile').get_attribute(
        'value') == ''


def test_browser_accessibility_semantics_and_keyboard_controls(browser):
    """Check accessible names, live regions, dialogs, and keyboard controls."""
    missing_names = browser.execute_script("""
      const text = (element) => element.textContent.trim();
      const name = (element) => {
        if (element.getAttribute('aria-label')) return true;
        if (element.getAttribute('aria-labelledby')) return true;
        if (element.labels &&
            [...element.labels].some((label) => text(label))) return true;
        return Boolean(text(element) || element.value || element.title);
      };
      return [...document.querySelectorAll('button, input, select, textarea')]
        .filter((element) => element.type !== 'hidden')
        .filter((element) => !name(element))
        .map((element) => element.id || element.outerHTML);
    """)
    assert missing_names == []

    if browser.capabilities['browserName'] == 'chrome':
        accessibility_tree = browser.execute_cdp_cmd(
            'Accessibility.getFullAXTree', {})
        interactive_roles = {
            'button', 'checkbox', 'combobox', 'searchbox', 'spinbutton',
            'textbox',
        }
        unnamed_interactive = [
            node['role']['value']
            for node in accessibility_tree['nodes']
            if node.get('role', {}).get('value') in interactive_roles and
            not node.get('name', {}).get('value')
        ]
        assert unnamed_interactive == []

    dialogs = browser.execute_script("""
      return [...document.querySelectorAll('dialog')].map((dialog) => ({
        id: dialog.id,
        label: dialog.getAttribute('aria-labelledby'),
        exists: Boolean(
          document.getElementById(dialog.getAttribute('aria-labelledby'))),
      }));
    """)
    assert dialogs
    assert all(dialog['label'] and dialog['exists'] for dialog in dialogs)

    progress = browser.find_element(By.ID, 'progressBar')
    assert progress.get_attribute('role') == 'progressbar'
    assert progress.get_attribute('aria-valuemax') == '100'

    browser.find_element(By.ID, 'newConfiguration').click()
    _wait(browser, lambda current: len(
        current.find_elements(By.CSS_SELECTOR, '.image-tab')) == 1)
    assert browser.find_element(By.ID, 'notice').get_attribute(
            'role') == 'status'
    browser.find_element(By.ID, 'newConfiguration').click()
    _wait(browser, lambda current: len(
        current.find_elements(By.CSS_SELECTOR, '.image-tab')) == 2)

    tabs = browser.find_elements(By.CSS_SELECTOR, '.image-tab')
    tabs[0].send_keys(Keys.ARROW_RIGHT)
    assert browser.switch_to.active_element.get_attribute(
            'class') == 'image-tab'
    assert len(browser.find_elements(
        By.CSS_SELECTOR, '.image-tab-close[aria-label^="Move left"]')) == 2
    assert len(browser.find_elements(
        By.CSS_SELECTOR, '.image-tab-close[aria-label^="Move right"]')) == 2

    browser.execute_script(
        "localStorage.setItem('chirp-web-view-preferences', '{broken');")
    browser.refresh()
    _wait(browser, conditions.presence_of_element_located(
            (By.ID, 'imageFile')))
    assert browser.title == 'CHIRP Web'
