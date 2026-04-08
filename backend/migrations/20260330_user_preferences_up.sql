/*
Run this only after taking a database backup on the server.
This script is idempotent and only creates the new table if it does not exist.
*/

IF OBJECT_ID(N'[dbo].[UserPreferences]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[UserPreferences] (
        [Username] NVARCHAR(255) NOT NULL,
        [ThemeColor] NVARCHAR(64) NULL,
        [CreatedAt] DATETIME2(0) NOT NULL
            CONSTRAINT [DF_UserPreferences_CreatedAt] DEFAULT SYSUTCDATETIME(),
        [UpdatedAt] DATETIME2(0) NOT NULL
            CONSTRAINT [DF_UserPreferences_UpdatedAt] DEFAULT SYSUTCDATETIME(),
        CONSTRAINT [PK_UserPreferences] PRIMARY KEY CLUSTERED ([Username] ASC)
    );
END;
