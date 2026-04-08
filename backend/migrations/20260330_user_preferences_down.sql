/*
Run this only after taking a database backup on the server.
This rollback keeps a copy of the data before dropping the feature table.
*/

IF OBJECT_ID(N'[dbo].[UserPreferences]', N'U') IS NOT NULL
BEGIN
    IF OBJECT_ID(N'[dbo].[UserPreferences_Backup_20260330]', N'U') IS NOT NULL
    BEGIN
        DROP TABLE [dbo].[UserPreferences_Backup_20260330];
    END;

    SELECT *
    INTO [dbo].[UserPreferences_Backup_20260330]
    FROM [dbo].[UserPreferences];

    DROP TABLE [dbo].[UserPreferences];
END;
