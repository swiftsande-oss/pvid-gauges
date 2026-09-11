# Regression testing outline (just getting started, Sept 2026)

At first, I'll do all of this manually.  Human eyes and fingers on every step.


## Start code transition

Empty sandbox if not already empty.

Save existing html, yml, py, in regression-tests/sandbox.

Copy Claude's new files from Downloads to their proper places in pvid-gauges.
Remember to rename Claude's explorer.html as index.html.

ExamDiff old files vs new files for overall sanity check---changes in logical places?

git pull, to refresh the local ...wide.csv file.  
Launch the local version of the website, using python launchFromMyPC.py

Open the public version of the website, in another window, maybe Edge or Chrome.

See that Version number looks ok.


## Ensure Season AF totals for prior years remain the same.

For each prior year's Season Totals button, save the htm into the sandbox.
Use ExamDiff to compare with what's in archives.


## ExamDiff 2025 wide.csv to archival copy. 

ExamDiff data\discharge_cfs_wide_2025.csv and regression-tests\archives\discharge_cfs_wide_2025.csv
Should be identical.

ExamDiff data\discharge_cfs_wide.csv and regression-tests\archives\discharge_cfs_wide.csv
Should be obvious that github has updated this file since the last time I updated the archive.  
If ok, update the copy in the archive.


## Look at the GUI, test every button.

Maybe have the live site open in Edge, the local site open in Firefox, side by side?


## Drill into gui and compare with checkingAgainstOrtizAceq.xls

In the local GUI, make the time interval the same as in checkingAgainstOrtizAceq.xls.

See if the cfs and AF graphs look identical.  

Check the total AF with the hover feature.


## Drill into gui and compare with screenshots assoc with tutorial video.

See archives\screenshots, and make the local GUI look the same.


## Finish

If all is good, upload to github.  Pull (so local data folder is current with the remote's refreshed data), Stage, Commit, Push.

Consider making an archival backup copy of everything in a separate folder.

Clean up regression-tests/sandbox.